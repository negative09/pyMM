"""Gaussian mixture models (GMMs).

Variants on GMMs including GMMs with full, diagonal and spherical covariance
matrices, as well as mixture of factor analysers (MFA) and mixture of
probabilistic principal component analysis models (MPPCA).

The EM algorithm is used to find maximum likelihood parameter estimates in the
presence of latent variables. The EM algorithm allows the models to handle
data that is missing at random (MAR).
"""

# Authors: Charlie Nash <charlie.nash@ed.ac.uk>
# License: MIT

import numpy as np
import scipy as sp
import numpy.random as rd

from random import seed
from scipy.stats import multivariate_normal
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA, FactorAnalysis
from sklearn.preprocessing import Imputer


class BaseModel(object):
    """ Base class for mixture models.

    This abstract class specifies an interface for all mixture classes and
    provides basic common methods for mixture models.
    """
    def __init__(self, n_components, tol=1e-3, max_iter=1000, random_state=0,
                 verbose=True, robust=False, SMALL=1e-5):
        self.n_components = n_components
        self.tol = tol
        self.max_iter = max_iter
        self.random_state = random_state
        self.verbose = verbose
        self.robust = robust
        self.isFitted = False
        self.SMALL = SMALL
        self.error_msg = (
            'Covariance matrix ill-conditioned. Use robust=True to ' +
            'pre-condition covariance matrices, increase SMALL or choose ' +
            'fewer mixture components'
            )

    def _get_log_responsibilities(self, X, mu_list, Sigma_list, components):
        """ Get log responsibilities for given parameters"""
        n_examples = X.shape[0]
        log_r = np.zeros([n_examples, self.n_components])
        for k, mu, Sigma in zip(range(self.n_components), mu_list,
                                Sigma_list):
            try:
                log_r[:, k] = multivariate_normal.logpdf(X, mu, Sigma)
            except (np.linalg.linalg.LinAlgError, ValueError):
                if self.robust:
                    Sigma_robust = Sigma + self.SMALL*np.eye(self.data_dim)
                    try:
                        log_r[:, k] = multivariate_normal.logpdf(X, mu,
                                                                 Sigma_robust)
                    except (np.linalg.linalg.LinAlgError, ValueError):
                        raise np.linalg.linalg.LinAlgError(self.error_msg)
                else:
                    raise np.linalg.linalg.LinAlgError(self.error_msg)
        log_r = log_r + np.log(components)
        log_r_sum = sp.misc.logsumexp(log_r, axis=1)
        responsibilities = np.exp(log_r - log_r_sum[:, np.newaxis])
        return log_r_sum, responsibilities

    def _get_log_responsibilities_miss(self, X, mu_list, Sigma_list,
                                       components, observed_list):
        """ Get log responsibilities for given parameters"""
        n_examples = X.shape[0]
        log_r = np.zeros([n_examples, self.n_components])
        for n in range(n_examples):
            id_obs = observed_list[n]
            row = X[n, :]
            row_obs = row[id_obs]
            for k, mu, Sigma in zip(range(self.n_components), mu_list,
                                    Sigma_list):
                mu_obs = mu[id_obs]
                Sigma_obs = Sigma[np.ix_(id_obs, id_obs)]
                try:
                    log_r[n, k] = (
                        multivariate_normal.logpdf(row_obs[np.newaxis, :],
                                                   mu_obs, Sigma_obs)
                        )
                except (np.linalg.linalg.LinAlgError, ValueError):
                    if self.robust:
                        Sigma_robust = (
                            Sigma_obs + self.SMALL*np.eye(self.data_dim)
                            )
                        try:
                            log_r[n, k] = (
                                multivariate_normal.logpdf(row_obs, mu_obs,
                                                           Sigma_robust)
                                )
                        except (np.linalg.linalg.LinAlgError, ValueError):
                            raise np.linalg.linalg.LinAlgError(self.error_msg)
                    else:
                        raise np.linalg.linalg.LinAlgError(self.error_msg)
        log_r = log_r + np.log(components)
        log_r_sum = sp.misc.logsumexp(log_r, axis=1)
        responsibilities = np.exp(log_r - log_r_sum[:, np.newaxis])
        return log_r_sum, responsibilities

    def _e_step(self, X, params):
        """ E-step of the EM-algorithm.

        Internal method used to call relevant e-step depending on the
        presence of missing data.
        """
        if self.missing_data:
            return self._e_step_miss(X, params)
        else:
            return self._e_step_no_miss(X, params)

    def _e_step_no_miss(self, X, params):
        """ E-Step of the EM-algorithm for complete data.

        The E-step takes the existing parameters, for the components, bias
        and noise variance and computes sufficient statistics for the M-Step
        by taking the expectation of latent variables conditional on the
        visible variables. Also returns the likelihood for the current
        parameters.

        Parameters
        ----------
        X : array, [nExamples, nFeatures]
            Matrix of training data, where nExamples is the number of
            examples and nFeatures is the number of features.

        params : dict
            Dictionary of parameters:

            params['Sigma_list'] : list of covariance matrices. One for each
                                   mixture component.

            params['mu_list'] : List of mean vectors. One for each mixture
                                component.

            params['components'] : Vector of component proportions. Represents
                                   the probability that the data comes from
                                   each component

        Returns
        -------
        ss : dict
            Dictionary of sufficient statistics:

                ss['r_list'] : Sum of responsibilities for each mixture
                               component.

                ss['x_list'] : Sum of data vectors weighted by component
                               responsibilties.

                ss['xx_list'] : Sum of outer products of data vectors weighted
                                by component responsibilities.

        sample_ll : array, [nExamples, ]
            log-likelihood for each example under the current parameters.
        """
        raise NotImplementedError()

    def _e_step_miss(self, X, params):
        """ E-Step of the EM-algorithm for missing data.

        The E-step takes the existing parameters, for the components, bias
        and noise variance and computes sufficient statistics for the M-Step
        by taking the expectation of latent variables conditional on the
        visible variables. Also returns the likelihood for the current
        parameters.

        Parameters
        ----------
        X : array, [nExamples, nFeatures]
            Matrix of training data, where nExamples is the number of
            examples and nFeatures is the number of features.

        params : dict
            Dictionary of parameters:

            params['Sigma_list'] : list of covariance matrices. One for each
                                   mixture component.

            params['mu_list'] : List of mean vectors. One for each mixture
                                component.

            params['components'] : Vector of component proportions. Represents
                                   the probability that the data comes from
                                   each component

        Returns
        -------
        ss : dict
            Dictionary of sufficient statistics:

                ss['r_list'] : Sum of responsibilities for each mixture
                               component.

                ss['x_list'] : Sum of data vectors weighted by component
                               responsibilties.

                ss['xx_list'] : Sum of outer products of data vectors weighted
                                by component responsibilities.

        sample_ll : array, [nExamples, ]
            log-likelihood for each example under the current parameters.
        """
        raise NotImplementedError()

    def _m_step(self, ss, params):
        """ M-Step of the EM-algorithm.

        The M-step takes the sufficient statistics computed in the E-step, and
        maximizes the expected complete data log-likelihood with respect to the
        parameters.

        Parameters
        ----------
        ss : dict
            Dictionary of sufficient statistics:

                ss['r_list'] : Sum of responsibilities for each mixture
                               component.

                ss['x_list'] : Sum of data vectors weighted by component
                               responsibilties.

                ss['xx_list'] : Sum of outer products of data vectors weighted
                                by component responsibilities.

        params : dict
            Dictionary of parameters:

            params['Sigma_list'] : list of covariance matrices. One for each
                                   mixture component.

            params['mu_list'] : List of mean vectors. One for each mixture
                                component.

            params['components'] : Vector of component proportions. Represents
                                   the probability that the data comes from
                                   each component

        Returns
        -------
        params : dict
            Updated dictionary of parameters. Keys as above.
        """
        raise NotImplementedError()

    def _params_to_Sigma(self, params):
        """ Converts parameter dictionary to covariance matrix list"""
        raise NotImplementedError()

    def _init_params(self, X, init_method='kmeans'):
        """ Initialize params"""
        raise NotImplementedError()

    def fit(self, X, params_init=None, init_method='kmeans'):
        """ Fit the model using EM with data X.

        Args
        ----
        X : array, [nExamples, nFeatures]
            Matrix of training data, where nExamples is the number of
            examples and nFeatures is the number of features.
        """
        if np.isnan(X).any():
            self.missing_data = True
        else:
            self.missing_data = False

        # Check for missing values and remove if whole row is missing
        X = X[~np.isnan(X).all(axis=1), :]
        n_examples, data_dim = np.shape(X)
        self.data_dim = data_dim
        self.n_examples = n_examples

        if params_init is None:
            params = self._init_params(X, init_method)
        else:
            params = params_init

        oldL = -np.inf
        for i in range(self.max_iter):

            # E-Step
            ss, sample_ll = self._e_step(X, params)

            # Evaluate likelihood
            ll = sample_ll.mean() / self.data_dim
            if self.verbose:
                print("Iter {:d}   NLL: {:.4f}   Change: {:.4f}".format(i,
                      -ll, -(ll-oldL)), flush=True)

            # Break if change in likelihood is small
            if np.abs(ll - oldL) < self.tol:
                break
            oldL = ll

            # M-step
            params = self._m_step(ss, params)

        else:
            if self.verbose:
                print("EM algorithm did not converge within the specified" +
                      " tolerance. You might want to increase the number of" +
                      " iterations.")

        # Update Object attributes
        self.params = params
        self.trainNll = ll
        self.isFitted = True

    def sample(self, n_samples=1):
        """Sample from fitted model.

        Sample from fitted model by first sampling from latent space
        (spherical Gaussian) then transforming into data space using learned
        parameters. Noise can then be added optionally.

        Parameters
        ----------
        nSamples : int
            Number of samples to generate
        noisy : bool
            Option to add noise to samples (default = True)

        Returns
        -------
        dataSamples : array [nSamples, dataDim]
            Collection of samples in data space.
        """
        if not self.isFitted:
            print("Model is not yet fitted. First use fit to learn the " +
                  "model params.")
        else:
            components = self.params['components']
            mu_list = self.params['mu_list']
            Sigma_list = self._params_to_Sigma(self.params)
            components_cumsum = np.cumsum(components)
            samples = np.zeros([n_samples, self.data_dim])
            for n in range(n_samples):
                r = np.random.rand(1)
                z = np.argmin(r > components_cumsum)
                samples[n] = rd.multivariate_normal(mu_list[z], Sigma_list[z])
            return samples

    def score_samples(self, X):
        if not self.isFitted:
            print("Model is not yet fitted. First use fit to learn the " +
                  "model params.")
        else:
            # Apply one step of E-step to get the sample log-likelihoods
            return self._e_step(X, self.params)[1] / self.data_dim

    def score(self, X):
        """Compute the average log-likelihood of data matrix X

        Parameters
        ----------
        X: array, shape (n_samples, n_features)
            The data

        Returns
        -------
        meanLl: array, shape (n_samples,)
            Log-likelihood of each sample under the current model
        """
        if not self.isFitted:
            print("Model is not yet fitted. First use fit to learn the " +
                  "model params.")
        else:
            # Apply one step of E-step to get the sample log-likelihoods
            sample_ll = self.score_samples(X)

            # Divide by number of examples to get average log likelihood
            return sample_ll.mean()


class GMM(BaseModel):
    """Gaussian Mixture Model (GMM).

    A mixture of Gaussians with unrestricted covariances.

    The GMM assumes the observed data is generated by first picking one of a
    number of mixture components then generating data from the Gaussian
    distribution associated with that component.

    The parameters of the model are the means, covariances and mixture
    coefficients for each mixture component.

    Maximum likelihood estimation of the model parameters is performed using
    the expectation-maximisation algorithm (EM).

    Parameters
    ----------
    n_components : int
        Number of mixture components to use

    tol : float
        Stopping tolerance for EM algorithm. The algorithm stops when the
        change in mean log-likelihood per data dimension is below tol.

    maxIter : int
        Maximum number of iterations for EM algorithm.

    random_state : int or RandomState
        Pseudo number generator state used for random sampling.

    verbose : bool
        Print output during fitting if true.

    robust : bool
        Whether to add a small number to the diagonal of covariance matrices
        in order to ensure positive definiteness.

    SMALL : float
        The small number used to improve the condition of covariance matrices.

    Attributes
    ----------

    isFitted : bool
        Whether or not the model is fitted.

    params : dict
        Dictionary of parameters:

        params['Sigma_list']: list of covariance matrices. One for each
                              mixture component.

        params['mu_list']: List of mean vectors. One for each mixture
                           component.

        params['components']: Vector of component proportions. Represents
                              the probability that the data comes from each
                              component


    missing_data : bool
        Indicates whether missing data is being used to fit the model.

    trainLL : float
        Mean training log-likelihood per dimension. Set after model is fitted.
    """

    def _e_step_no_miss(self, X, params):
        """ E-Step of the EM-algorithm for complete data.

        The E-step takes the existing parameters, for the components, bias
        and noise variance and computes sufficient statistics for the M-Step
        by taking the expectation of latent variables conditional on the
        visible variables. Also returns the likelihood for the current
        parameters.

        Parameters
        ----------
        X : array, [nExamples, nFeatures]
            Matrix of training data, where nExamples is the number of
            examples and nFeatures is the number of features.

        params : dict
            Dictionary of parameters:

            params['Sigma_list'] : list of covariance matrices. One for each
                                   mixture component.

            params['mu_list'] : List of mean vectors. One for each mixture
                                component.

            params['components'] : Vector of component proportions. Represents
                                   the probability that the data comes from
                                   each component

        Returns
        -------
        ss : dict
            Dictionary of sufficient statistics:

                ss['r_list'] : Sum of responsibilities for each mixture
                               component.

                ss['x_list'] : Sum of data vectors weighted by component
                               responsibilties.

                ss['xx_list'] : Sum of outer products of data vectors weighted
                                by component responsibilities.

        sample_ll : array, [nExamples, ]
            log-likelihood for each example under the current parameters.
        """
        # Get params
        mu_list = params['mu_list']
        components = params['components']

        # Get Sigma from params
        Sigma_list = self._params_to_Sigma(params)

        # Compute responsibilities
        log_r_sum, responsibilities = (
            self._get_log_responsibilities(X, mu_list, Sigma_list, components)
            )

        # Get sufficient statistics
        x_list = [np.sum(X*r[:, np.newaxis], axis=0) for r in
                  responsibilities.T]
        xx_list = [np.sum(X[:, :, np.newaxis] * X[:, np.newaxis, :] *
                          r[:, np.newaxis, np.newaxis], axis=0) for r in
                   responsibilities.T]
        r_list = [r.sum() for r in responsibilities.T]

        # Store sufficient statistics in dictionary
        ss = {'r_list': r_list,
              'x_list': x_list,
              'xx_list': xx_list}

        # Compute log-likelihood of each example
        sample_ll = log_r_sum

        return ss, sample_ll

    def _e_step_miss(self, X, params):
        """ E-Step of the EM-algorithm for missing data.

        The E-step takes the existing parameters, for the components, bias
        and noise variance and computes sufficient statistics for the M-Step
        by taking the expectation of latent variables conditional on the
        visible variables. Also returns the likelihood for the current
        parameters.

        Parameters
        ----------
        X : array, [nExamples, nFeatures]
            Matrix of training data, where nExamples is the number of
            examples and nFeatures is the number of features.

        params : dict
            Dictionary of parameters:

            params['Sigma_list'] : list of covariance matrices. One for each
                                   mixture component.

            params['mu_list'] : List of mean vectors. One for each mixture
                                component.

            params['components'] : Vector of component proportions. Represents
                                   the probability that the data comes from
                                   each component

        Returns
        -------
        ss : dict
            Dictionary of sufficient statistics:

                ss['r_list'] : Sum of responsibilities for each mixture
                               component.

                ss['x_list'] : Sum of data vectors weighted by component
                               responsibilties.

                ss['xx_list'] : Sum of outer products of data vectors weighted
                                by component responsibilities.

        sample_ll : array, [nExamples, ]
            log-likelihood for each example under the current parameters.
        """
        # Get current params
        mu_list = params['mu_list']
        components = params['components']

        # Get Sigma from params
        Sigma_list = self._params_to_Sigma(params)

        observed_list = [np.array(np.where(~np.isnan(row))).flatten() for
                         row in X]
        n_examples, data_dim = np.shape(X)

        # Compute responsibilities
        log_r_sum, responsibilities = (
            self._get_log_responsibilities_miss(X, mu_list, Sigma_list,
                                                components, observed_list)
            )

        # Get sufficient statistics
        r_list = [r.sum() for r in responsibilities.T]
        x_list = []
        xx_list = []
        for k, mu, Sigma, r in zip(range(self.n_components), mu_list,
                                   Sigma_list, responsibilities.T):

            x_tot = np.zeros(data_dim)
            xx_tot = np.zeros([data_dim, data_dim])
            for n in range(n_examples):
                id_obs = observed_list[n]
                id_miss = np.setdiff1d(np.arange(data_dim), id_obs)
                n_miss = len(id_miss)
                row = X[n, :]
                row_obs = row[id_obs]

                # Simplify for case with no missing data
                if n_miss == 0:
                    x_tot += row_obs * r[n]
                    xx_tot += np.outer(row_obs, row_obs) * r[n]
                    continue

                # Get missing / present parameters
                mu_obs = mu[id_obs]
                mu_miss = mu[id_miss]
                Sigma_obs = Sigma[np.ix_(id_obs, id_obs)]
                Sigma_miss = Sigma[np.ix_(id_miss, id_miss)]
                Sigma_obs_miss = Sigma[np.ix_(id_obs, id_miss)]
                Sigma_miss_obs = Sigma[np.ix_(id_miss, id_obs)]

                # Get conditional distribution p(x_miss | x_vis, params_k)
                Sigma_obs_inv = np.linalg.pinv(Sigma_obs)
                mean_cond = (
                    mu_miss +
                    Sigma_miss_obs @ Sigma_obs_inv @ (row_obs - mu_obs)
                    )
                Sigma_cond = (
                    Sigma_miss -
                    Sigma_miss_obs @ Sigma_obs_inv @ Sigma_obs_miss
                    )

                # Get sufficient statistics E[x]
                x = np.empty(data_dim)
                x[id_obs] = row_obs
                x[id_miss] = mean_cond
                x_tot += x * r[n]

                # Get sufficient statistic E[xx^t]
                xx = np.empty([data_dim, data_dim])
                xx[np.ix_(id_obs, id_obs)] = np.outer(row_obs, row_obs)
                xx[np.ix_(id_obs, id_miss)] = np.outer(row_obs, mean_cond)
                xx[np.ix_(id_miss, id_obs)] = np.outer(mean_cond, row_obs)
                xx[np.ix_(id_miss, id_miss)] = (
                    np.outer(mean_cond, mean_cond) + Sigma_cond
                    )
                xx_tot += xx * r[n]
            x_list.append(x_tot)
            xx_list.append(xx_tot)

        # Store sufficient statistics in dictionary
        ss = {'r_list': r_list,
              'x_list': x_list,
              'xx_list': xx_list}

        # Compute log-likelihood of each example
        sample_ll = log_r_sum

        return ss, sample_ll

    def _m_step(self, ss, params):
        """ M-Step of the EM-algorithm.

        The M-step takes the sufficient statistics computed in the E-step, and
        maximizes the expected complete data log-likelihood with respect to the
        parameters.

        Parameters
        ----------
        ss : dict
            Dictionary of sufficient statistics:

                ss['r_list'] : Sum of responsibilities for each mixture
                               component.

                ss['x_list'] : Sum of data vectors weighted by component
                               responsibilties.

                ss['xx_list'] : Sum of outer products of data vectors weighted
                                by component responsibilities.

        params : dict
            Dictionary of parameters:

            params['Sigma_list'] : list of covariance matrices. One for each
                                   mixture component.

            params['mu_list'] : List of mean vectors. One for each mixture
                                component.

            params['components'] : Vector of component proportions. Represents
                                   the probability that the data comes from
                                   each component

        Returns
        -------
        params : dict
            Updated dictionary of parameters. Keys as above.
        """
        r_list = ss['r_list']
        x_list = ss['x_list']
        xx_list = ss['xx_list']
        n_examples = self.n_examples

        # Update components param
        components = np.array([r/n_examples for r in r_list])

        # Update mean / Sigma params
        mu_list = []
        Sigma_list = []
        for r, x, xx in zip(r_list, x_list, xx_list):
            mu = x / r
            mu_list.append(mu)
            Sigma = xx / r - np.outer(mu, mu)
            Sigma_list.append(Sigma)

        # Store params in dictionary
        params = {'Sigma_list': Sigma_list,
                  'mu_list': mu_list,
                  'components': components}

        return params

    def _params_to_Sigma(self, params):
        """ Converts parameter dictionary to covariance matrix list"""
        return params['Sigma_list']

    def _init_params(self, X, init_method='kmeans'):
        seed(self.random_state)
        n_examples = X.shape[0]
        if init_method == 'kmeans':
            kmeans = KMeans(self.n_components)
            if self.missing_data:
                imputer = Imputer()
                X = imputer.fit_transform(X)
            kmeans.fit(X)
            mu_list = [k for k in kmeans.cluster_centers_]
            Sigma_list = []
            for k in range(self.n_components):
                X_k = X[kmeans.labels_ == k, :]
                n_k = X_k.shape[0]
                if n_k == 1:
                    Sigma_list.append(0.1*np.eye(self.data_dim))
                else:
                    Sigma_list.append(np.cov(X_k.T))
            components = np.array([np.sum(kmeans.labels_ == k) / n_examples
                                  for k in range(self.n_components)])
            params_init = {'mu_list': mu_list,
                           'Sigma_list': Sigma_list,
                           'components': components}
            return params_init


class SphericalGMM(GMM):

    @staticmethod
    def _convert_gmm_params(params):
        sigma_sq_list = [np.mean(np.diag(cov)) for cov in
                         params['Sigma_list']]
        params_conv = {i: params[i] for i in params if i != 'Sigma_list'}
        params_conv['sigma_sq_list'] = sigma_sq_list
        return params_conv

    def _init_params(self, X, init_method='kmeans'):
        params_init_gmm = (
            super(SphericalGMM, self)._init_params(X, init_method)
            )
        return self._convert_gmm_params(params_init_gmm)

    def _m_step(self, ss, params):
        params_gmm = super(SphericalGMM, self)._m_step(ss, params)
        return self._convert_gmm_params(params_gmm)

    def _params_to_Sigma(self, params):
        return [sigma_sq*np.eye(self.data_dim) for sigma_sq in
                params['sigma_sq_list']]


class DiagonalGMM(SphericalGMM):

    @staticmethod
    def _convert_gmm_params(params):
        Psi_list = [np.diag(np.diag(cov)) for cov in params['Sigma_list']]
        params_conv = {i: params[i] for i in params if i != 'Sigma_list'}
        params_conv['Psi_list'] = Psi_list
        return params_conv

    def _params_to_Sigma(self, params):
            return params['Psi_list']


class MPPCA(GMM):
    """Mixtures of probabilistic principal components analysis (PPCA) models.

    A generative latent variable model.

    PPCA assumes that the observed data is generated by first generating latent
    variables z from a Gaussian distribution p(z), then linearly transforming
    these variables with a weights matrix W, and then finally adding spherical
    Gaussian noise. PPCA can be viewed as a Gaussian model with a low-rank
    approximation to the covariance matrix. It can be useful in the case
    where there are many dimensions, but not many examples. Here a
    full-covariance model needs to estimate many parameters, and will have a
    tendency to overfit, whereas a PPCA model can have considerably fewer
    parameters, and therefore is less likely to overfit.

    The parameters of the model are the transformation matrix W , the mean mu,
    and the noise variance sigma_sq.

    The mixture of PPCA models (MPPCA) additionally assumes that the data can
    come from a number of PPCA components, with each component being selected
    from a disrete probability distribution. Thus the parameters are W_k, mu_k
    and sigma_sq_k for each component k, and component probabilities alpha_k
    for each component.

    MPPCA performs maximum likelihood or MAP estimation of the model
    parameters using the expectation-maximisation algorithm (EM algorithm).

    Attributes
    ----------

    latent_dim : int
        Dimensionality of latent space. The number of variables that are
        transformed by the weight matrix to the data space.

    n_components : array, [latentDim, nFeatures]
        Transformation matrix parameter.

    bias: array, [nFeatures]
        Bias parameter.

    noiseVariance : float
        Noise variance parameter. Variance of noise that is added to linearly
        transformed latent variables to generate data.

    standardize : bool, optional
        When True, the mean is subtracted from the data, and each feature is
        divided by it's standard deviation so that the mean and variance of
        the transformed features are 0 and 1 respectively.

    componentPrior : float >= 0
        Gaussian component matrix hyperparameter. If > 0 then a Gaussian prior
        is applied to each column of the component matrix with covariance
        componentPrior^-1 * noiseVariance. This has the effect
        of regularising the component matrix.

    tol : float
        Stopping tolerance for EM algorithm

    maxIter : int
        Maximum number of iterations for EM algorithm
    """

    def __init__(self, n_components, latent_dim, tol=1e-3, max_iter=1000,
                 random_state=0, verbose=True, robust=False, SMALL=1e-5):

        super(MPPCA, self).__init__(
            n_components=n_components, tol=tol, max_iter=max_iter,
            random_state=random_state, verbose=verbose, robust=robust,
            SMALL=SMALL
            )
        self.latent_dim = latent_dim

    def _init_params(self, X, init_method='kmeans'):
        seed(self.random_state)
        n_examples = X.shape[0]
        if init_method == 'kmeans':
            kmeans = KMeans(self.n_components)
            if self.missing_data:
                imputer = Imputer()
                X = imputer.fit_transform(X)
            kmeans.fit(X)
            n_clust_list = [(kmeans.labels_ == i).sum() for i in
                            range(self.n_components)]
            print(n_clust_list)
            mu_list = [k for k in kmeans.cluster_centers_]
            W_list = []
            sigma_sq_list = []
            for k, n_clust in enumerate(n_clust_list):
                if n_clust >= self.latent_dim:
                    data_k = X[kmeans.labels_ == k, :]
                    pca = PCA(n_components=self.latent_dim)
                    pca.fit(data_k)
                    W_list.append(pca.components_.T)
                else:
                    W_list.append(np.random.randn(self.data_dim,
                                                  self.latent_dim))
                sigma_sq_list.append(0.1)
#                sigma_sq_list.append(pca.noise_variance_)
            components = np.array([np.sum(kmeans.labels_ == k) / n_examples
                                   for k in range(self.n_components)])
            params_init = {'mu_list': mu_list,
                           'W_list': W_list,
                           'sigma_sq_list': sigma_sq_list,
                           'components': components}
            return params_init

    def _e_step_no_miss(self, X, params):
        """ E-Step of the EM-algorithm.

        The E-step takes the existing parameters, for the components, bias
        and noise variance and computes sufficient statistics for the M-Step
        by taking the expectation of latent variables conditional on the
        visible variables. Also returns the likelihood for the data X and
        projections into latent space of the data.

        Args
        ----
        X : array, [nExamples, nFeatures]
            Matrix of training data, where nExamples is the number of
            examples and nFeatures is the number of features.
        W : array, [dataDim, latentDim]
            Component matrix data. Maps latent points to data space.
        b : array, [dataDim,]
            Data bias.
        sigmaSq : float
            Noise variance parameter.

        Returns
        -------
        ss : dict

        proj :

        ll :
        """
        # Get params
        mu_list = params['mu_list']
        components = params['components']
        W_list = params['W_list']
        sigma_sq_list = params['sigma_sq_list']
        n_examples, data_dim = X.shape

        # Get Sigma from params
        Sigma_list = self._params_to_Sigma(params)

        # Compute responsibilities
        log_r_sum, responsibilities = (
            self._get_log_responsibilities(X, mu_list, Sigma_list, components)
            )

        # Get sufficient statistics for each component
        r_list = [r.sum() for r in responsibilities.T]
        x_list = []
        z_list = []
        zz_list = []
        xz_list = []
        ss_list = []
        for mu, W, sigma_sq, r in zip(mu_list, W_list, sigma_sq_list,
                                      responsibilities.T):
            dev = X - mu
            F_inv = np.linalg.inv(W.T @ W + sigma_sq*np.eye(self.latent_dim))

            x_list.append(np.sum(X*r[:, np.newaxis], axis=0))

            z = dev @ W @ F_inv
            z_list.append(np.sum(z*r[:, np.newaxis], axis=0))

            zz = sigma_sq*F_inv + z[:, :, np.newaxis] * z[:, np.newaxis, :]
            zz_list.append(np.sum(zz*r[:, np.newaxis, np.newaxis], axis=0))

            xz = dev[:, :, np.newaxis] * z[:, np.newaxis, :]
            xz_list.append(np.sum(xz*r[:, np.newaxis, np.newaxis], axis=0))

            xx = dev[:, :, np.newaxis] * dev[:, np.newaxis, :]
            s1 = np.trace(xx, axis1=1, axis2=2)
            s2 = -2*np.trace(xz @ W.T, axis1=1, axis2=2)
            s3 = np.trace(zz * (W.T @ W), axis1=1, axis2=2)
            ss_list.append(np.sum(r*(s1 + s2 + s3)))

        # Store sufficient statistics in dictionary
        ss = {'r_list': r_list,
              'x_list': x_list,
              'xz_list': xz_list,
              'z_list': z_list,
              'zz_list': zz_list,
              'ss_list': ss_list}

        # Compute log-likelihood
        sample_ll = log_r_sum

        return ss, sample_ll

    def _e_step_miss(self, X, params):
        """ E-Step of the EM-algorithm.

        The E-step takes the existing parameters, for the components, bias
        and noise variance and computes sufficient statistics for the M-Step
        by taking the expectation of latent variables conditional on the
        visible variables. Also returns the likelihood for the data X and
        projections into latent space of the data.

        Args
        ----
        X : array, [nExamples, nFeatures]
            Matrix of training data, where nExamples is the number of
            examples and nFeatures is the number of features.
        W : array, [dataDim, latentDim]
            Component matrix data. Maps latent points to data space.
        b : array, [dataDim,]
            Data bias.
        sigmaSq : float
            Noise variance parameter.

        Returns
        -------
        ss : dict

        proj :

        ll :
        """
        # Get current params
        mu_list = params['mu_list']
        components = params['components']
        sigma_sq_list = params['sigma_sq_list']
        W_list = params['W_list']

        # Get Sigma from params
        Sigma_list = self._params_to_Sigma(params)

        observed_list = [
            np.array(np.where(~np.isnan(row))).flatten() for row in X
            ]
        n_examples, data_dim = np.shape(X)

        # Compute responsibilities
        log_r_sum, responsibilities = (
            self._get_log_responsibilities_miss(X, mu_list, Sigma_list,
                                                components, observed_list)
            )

        # Get sufficient statistics for each component
        r_list = [r.sum() for r in responsibilities.T]
        x_list = []
        z_list = []
        zz_list = []
        xz_list = []
        ss_list = []
        for mu, W, sigma_sq, r in zip(mu_list, W_list, sigma_sq_list,
                                      responsibilities.T):
            x_tot = np.zeros(data_dim)
            z_tot = np.zeros(self.latent_dim)
            zz_tot = np.zeros([self.latent_dim, self.latent_dim])
            xz_tot = np.zeros([self.data_dim, self.latent_dim])
            ss_tot = 0
            for n in range(n_examples):
                id_obs = observed_list[n]
                id_miss = np.setdiff1d(np.arange(data_dim), id_obs)
                n_miss = len(id_miss)
                row = X[n, :]
                row_obs = row[id_obs]

                # Get missing and visible points
                W_obs = W[id_obs, :]
                W_miss = W[id_miss, :]
                mu_obs = mu[id_obs]
                mu_miss = mu[id_miss]
                row_min_mu = row_obs - mu_obs

                # Get conditional distribution of p(z | x_vis, params)
                F_inv = np.linalg.inv(W_obs.T @ W_obs +
                                      sigma_sq*np.eye(self.latent_dim))
                cov_z_cond = sigma_sq*F_inv
                mean_z_cond = F_inv @ W_obs.T @ (row_obs - mu_obs)

                # Simplify for case with no missing data
                if n_miss == 0:
                    x_tot += row_obs*r[n]
                    z_tot += mean_z_cond*r[n]
                    zz = cov_z_cond + np.outer(mean_z_cond, mean_z_cond)
                    zz_tot += zz*r[n]
                    xz = np.outer(row_min_mu, mean_z_cond)
                    xz_tot += xz*r[n]
                    xx = np.outer(row_min_mu, row_min_mu)
                    s1 = np.trace(xx)
                    s2 = -2*np.trace(xz @ W.T)
                    s3 = np.trace(zz * W.T @ W)
                    ss_tot += (s1 + s2 + s3)*r[n]
                    continue

                # Get conditional distribution of p(x_miss | z, params)
                mean_x_miss = W_miss @ mean_z_cond + mu_miss

                # Append sufficient statistics
                z_tot += mean_z_cond*r[n]
                zz = cov_z_cond + np.outer(mean_z_cond, mean_z_cond)
                zz_tot += zz*r[n]

                x_tot[id_obs] += row_obs*r[n]
                x_tot[id_miss] += mean_x_miss*r[n]

                xz = np.zeros([self.data_dim, self.latent_dim])
                xz[id_miss, :] = W_miss @ zz
                xz[id_obs, :] = np.outer(row_min_mu, mean_z_cond)
                xz_tot += xz*r[n]

                xx = np.empty([data_dim, data_dim])
                xx[np.ix_(id_obs, id_obs)] = np.outer(row_min_mu, row_min_mu)
                xx[np.ix_(id_obs, id_miss)] = (
                    np.outer(row_min_mu, mean_x_miss - mu_miss)
                    )
                xx[np.ix_(id_miss, id_obs)] = (
                    np.outer(mean_x_miss - mu_miss, row_min_mu)
                    )
                xx[np.ix_(id_miss, id_miss)] = (
                    W_miss @ zz @ W_miss.T + sigma_sq*np.eye(n_miss)
                    )
                s1 = np.trace(xx)
                s2 = -2*np.trace(xz @ W.T)
                s3 = np.trace(zz * W.T @ W)
                ss_tot += (s1 + s2 + s3)*r[n]

            x_list.append(x_tot)
            z_list.append(z_tot)
            zz_list.append(zz_tot)
            xz_list.append(xz_tot)
            ss_list.append(ss_tot)

        # Store sufficient statistics in dictionary
        ss = {'r_list': r_list,
              'x_list': x_list,
              'xz_list': xz_list,
              'z_list': z_list,
              'zz_list': zz_list,
              'ss_list': ss_list}

        # Compute log-likelihood
        sample_ll = log_r_sum

        return ss, sample_ll

    def _m_step(self, ss, params):
        """ M-Step of the EM-algorithm.

        The M-step takes the sufficient statistics computed in the E-step, and
        maximizes the expected complete data log-likelihood with respect to the
        parameters.

        Args
        ----
        ss : dict

        Returns
        -------
        params : dict

        """
        n_examples = self.n_examples
        r_list = ss['r_list']
        x_list = ss['x_list']
        z_list = ss['z_list']
        zz_list = ss['zz_list']
        xz_list = ss['xz_list']
        ss_list = ss['ss_list']
        W_list_old = params['W_list']

        # Update components param
        components = np.array([r / n_examples for r in r_list])

        # Update mean / Sigma params
        mu_list = []
        W_list = []
        sigma_sq_list = []
        for r, W, x, z, zz, xz, ss in zip(r_list, W_list_old, x_list, z_list,
                                          zz_list, xz_list, ss_list):
            resid = x - W.dot(z)
            mu = resid / r
            mu_list.append(mu)

            W = np.linalg.solve(zz, xz.T).T
            W_list.append(W)

            sigma_sq = ss / (self.data_dim * r)
            sigma_sq_list.append(sigma_sq)

        # Store params in dictionary
        params = {'W_list': W_list,
                  'sigma_sq_list': sigma_sq_list,
                  'mu_list': mu_list,
                  'components': components}
        return params

    def _params_to_Sigma(self, params):
        W_list = params['W_list']
        sigma_sq_list = params['sigma_sq_list']
        Sigma_list = [W @ W.T + sigma_sq*np.eye(self.data_dim)
                      for W, sigma_sq in zip(W_list, sigma_sq_list)]
        return Sigma_list


class MFA(GMM):

    def __init__(self, n_components, latent_dim, tol=1e-3, max_iter=1000,
                 random_state=0, verbose=True, robust=False, SMALL=1e-5):
        super(MFA, self).__init__(n_components=n_components, tol=tol,
                                  max_iter=max_iter,
                                  random_state=random_state,
                                  verbose=verbose, robust=robust,
                                  SMALL=SMALL)
        self.latent_dim = latent_dim

    def _init_params(self, X, init_method='kmeans'):
        seed(self.random_state)
        n_examples = X.shape[0]
        if init_method == 'kmeans':
            kmeans = KMeans(self.n_components)
            if self.missing_data:
                imputer = Imputer()
                X = imputer.fit_transform(X)
            kmeans.fit(X)
            mu_list = [k + 0*np.random.randn(self.data_dim) for k in
                       kmeans.cluster_centers_]
            W_list = []
            Psi_list = []
            for k in range(self.n_components):
                X_k = X[kmeans.labels_ == k, :]
                if 1 == X_k.shape[0]:
                    W_list.append(1e-5 * np.random.randn(self.data_dim,
                                                         self.latent_dim))
                    Psi_list.append(0.1*np.eye(self.data_dim))
                elif X_k.shape[0] < self.data_dim:
                    W_list.append(1e-5 * np.random.randn(self.data_dim,
                                                         self.latent_dim))
                    Psi_list.append(np.diag(np.diag(np.cov(X_k.T))))
                else:
                    fa = FactorAnalysis(n_components=self.latent_dim)
                    fa.fit(X_k)
                    W_list.append(fa.components_.T)
                    Psi_list.append(np.diag(fa.noise_variance_))
            components = np.array([np.sum(kmeans.labels_ == k) / n_examples
                                   for k in range(self.n_components)])
            if np.min(components)*n_examples == 1:
                print('Warning: Components initialised with only one data ' +
                      'point. Poor results expected. Consider using fewer ' +
                      'components.')
            params_init = {'mu_list': mu_list,
                           'W_list': W_list,
                           'Psi_list': Psi_list,
                           'components': components}
            return params_init

    def _e_step_no_miss(self, X, params):
        """ E-Step of the EM-algorithm.

        The E-step takes the existing parameters, for the components, bias
        and noise variance and computes sufficient statistics for the M-Step
        by taking the expectation of latent variables conditional on the
        visible variables. Also returns the likelihood for the data X and
        projections into latent space of the data.

        Args
        ----
        X : array, [nExamples, nFeatures]
            Matrix of training data, where nExamples is the number of
            examples and nFeatures is the number of features.
        W : array, [dataDim, latentDim]
            Component matrix data. Maps latent points to data space.
        b : array, [dataDim,]
            Data bias.
        sigmaSq : float
            Noise variance parameter.

        Returns
        -------
        ss : dict

        proj :

        ll :
        """
        # Get params
        mu_list = params['mu_list']
        components = params['components']
        W_list = params['W_list']
        Psi_list = params['Psi_list']
        n_examples, data_dim = X.shape

        # Get Sigma from params
        Sigma_list = self._params_to_Sigma(params)

        # Compute responsibilities
        log_r_sum, responsibilities = (
            self._get_log_responsibilities(X, mu_list, Sigma_list, components)
            )

        # Get sufficient statistics E[z] and E[zz^t] for each component
        r_list = [r.sum() for r in responsibilities.T]
        x_list = []
        z_list = []
        zz_list = []
        xz_list = []
        zx_list = []
        xx_list = []
        for mu, W, Psi, r in zip(mu_list, W_list, Psi_list,
                                 responsibilities.T):
            dev = X - mu
            F = W @ W.T + Psi
            try:
                F_inv_W = np.linalg.solve(F, W)
            except np.linalg.linalg.LinAlgError:
                if self.robust:
                    F_robust = F + self.SMALL*np.eye(self.data_dim)
                    F_inv_W = np.linalg.solve(F_robust, W)
                else:
                    raise np.linalg.linalg.LinAlgError(self.error_msg)
            x_list.append(np.sum(X*r[:, np.newaxis], axis=0))
            z = dev @ F_inv_W
            z_list.append(np.sum(z*r[:, np.newaxis], axis=0))
            zz = (np.eye(self.latent_dim) - W.T @ F_inv_W +
                  z[:, :, np.newaxis] * z[:, np.newaxis, :])
            zz_list.append(np.sum(zz*r[:, np.newaxis, np.newaxis], axis=0))
            xx = dev[:, :, np.newaxis] * dev[:, np.newaxis, :]
            xx_list.append(np.sum(xx*r[:, np.newaxis, np.newaxis], axis=0))
            xz = dev[:, :, np.newaxis] * z[:, np.newaxis, :]
            xz_list.append(np.sum(xz*r[:, np.newaxis, np.newaxis], axis=0))
            zx = z[:, :, np.newaxis] * dev[:, np.newaxis, :]
            zx_list.append(np.sum(zx*r[:, np.newaxis, np.newaxis], axis=0))

        # Store sufficient statistics in dictionary
        ss = {'r_list': r_list,
              'x_list': x_list,
              'xx_list': xx_list,
              'xz_list': xz_list,
              'zx_list': zx_list,
              'z_list': z_list,
              'zz_list': zz_list}

        # Compute log-likelihood
        sample_ll = log_r_sum

        return ss, sample_ll

    def _e_step_miss(self, X, params):
        """ E-Step of the EM-algorithm.

        The E-step takes the existing parameters, for the components, bias
        and noise variance and computes sufficient statistics for the M-Step
        by taking the expectation of latent variables conditional on the
        visible variables. Also returns the likelihood for the data X and
        projections into latent space of the data.

        Args
        ----
        X : array, [nExamples, nFeatures]
            Matrix of training data, where nExamples is the number of
            examples and nFeatures is the number of features.
        W : array, [dataDim, latentDim]
            Component matrix data. Maps latent points to data space.
        b : array, [dataDim,]
            Data bias.
        sigmaSq : float
            Noise variance parameter.

        Returns
        -------
        ss : dict

        proj :

        ll :
        """
        # Get current params
        mu_list = params['mu_list']
        components = params['components']
        Psi_list = params['Psi_list']
        W_list = params['W_list']

        # Get Sigma from params
        Sigma_list = self._params_to_Sigma(params)
        observed_list = [np.array(np.where(~np.isnan(row))).flatten() for
                         row in X]
        n_examples, data_dim = np.shape(X)

        # Compute responsibilities
        log_r_sum, responsibilities = (
            self._get_log_responsibilities_miss(X, mu_list, Sigma_list,
                                                components, observed_list)
            )

        # Get sufficient statistics for each component
        r_list = [r.sum() for r in responsibilities.T]
        x_list = []
        xx_list = []
        z_list = []
        zz_list = []
        xz_list = []
        zx_list = []
        for mu, W, Psi, r in zip(mu_list, W_list, Psi_list,
                                 responsibilities.T):
            Psi_inv = np.diag(1/np.diag(Psi))
            x_tot = np.zeros(data_dim)
            xx_tot = np.zeros([data_dim, data_dim])
            z_tot = np.zeros([self.latent_dim])
            zz_tot = np.zeros([self.latent_dim, self.latent_dim])
            xz_tot = np.zeros([self.data_dim, self.latent_dim])
            zx_tot = np.zeros([self.latent_dim, self.data_dim])

            for n in range(n_examples):
                id_obs = observed_list[n]
                id_miss = np.setdiff1d(np.arange(data_dim), id_obs)
                n_miss = len(id_miss)
                row = X[n, :]
                row_obs = row[id_obs]

                # Get missing and visible parameters
                Psi_miss = Psi[np.ix_(id_miss, id_miss)]
                Psi_inv_obs = Psi_inv[np.ix_(id_obs, id_obs)]
                W_obs = W[id_obs, :]
                W_miss = W[id_miss, :]
                mu_obs = mu[id_obs]
                mu_miss = mu[id_miss]
                row_min_mu = row_obs - mu_obs

                # Get conditional distribution of p(z | x_vis, params) using
                # the woodbury identity

                Beta = (
                    Psi_inv_obs - Psi_inv_obs @ W_obs @
                    np.linalg.solve(
                        W_obs.T @ Psi_inv_obs @ W_obs +
                        np.eye(self.latent_dim),
                        W_obs.T @ Psi_inv_obs)
                    )
                mean_z_cond = W_obs.T @ Beta @ row_min_mu
                cov_z_cond = np.eye(self.latent_dim) - W_obs.T @ Beta @ W_obs

                # Simplify for case with no missing data
                if n_miss == 0:
                    x_tot += row_obs*r[n]
                    z_tot += mean_z_cond*r[n]
                    zz = cov_z_cond + np.outer(mean_z_cond, mean_z_cond)
                    zz_tot += zz*r[n]
                    xz = np.outer(row_min_mu, mean_z_cond)
                    xz_tot += xz*r[n]
                    zx = xz.T
                    zx_tot += zx*r[n]
                    xx = np.outer(row_min_mu, row_min_mu)
                    xx_tot += xx*r[n]
                    continue

                # Get conditional distribution of p(x_miss | z, params)
                mean_x_miss = W_miss.dot(mean_z_cond) + mu_miss

                # Append sufficient statistics
                z_tot += mean_z_cond*r[n]
                zz = cov_z_cond + np.outer(mean_z_cond, mean_z_cond)
                zz_tot += zz

                x_tot[id_obs] += row_obs*r[n]
                x_tot[id_miss] += mean_x_miss*r[n]

                xz = np.zeros([self.data_dim, self.latent_dim])
                xz[id_miss, :] = W_miss @ zz
                xz[id_obs, :] = np.outer(row_min_mu, mean_z_cond)
                xz_tot += xz*r[n]

                zx = xz.T
                zx_tot += zx*r[n]

                xx = np.empty([data_dim, data_dim])
                xx[np.ix_(id_obs, id_obs)] = np.outer(row_min_mu, row_min_mu)
                xx[np.ix_(id_obs, id_miss)] = np.outer(row_min_mu,
                                                       mean_x_miss - mu_miss)
                xx[np.ix_(id_miss, id_obs)] = np.outer(mean_x_miss - mu_miss,
                                                       row_min_mu)
                xx[np.ix_(id_miss, id_miss)] = (
                    W_miss @ zz @ W_miss.T + Psi_miss
                    )
                xx_tot += xx*r[n]
            x_list.append(x_tot)
            xx_list.append(xx_tot)
            z_list.append(z_tot)
            zz_list.append(zz_tot)
            xz_list.append(xz_tot)
            zx_list.append(zx_tot)

        # Store sufficient statistics in dictionary
        ss = {'r_list': r_list,
              'x_list': x_list,
              'xx_list': xx_list,
              'xz_list': xz_list,
              'zx_list': zx_list,
              'z_list': z_list,
              'zz_list': zz_list}

        # Compute log-likelihood
        sample_ll = log_r_sum

        return ss, sample_ll

    def _m_step(self, ss, params):
        """ M-Step of the EM-algorithm.

        The M-step takes the sufficient statistics computed in the E-step, and
        maximizes the expected complete data log-likelihood with respect to the
        parameters.

        Args
        ----
        ss : dict

        Returns
        -------
        params : dict

        """
        n_examples = self.n_examples
        r_list = ss['r_list']
        x_list = ss['x_list']
        xx_list = ss['xx_list']
        xz_list = ss['xz_list']
        zx_list = ss['zx_list']
        z_list = ss['z_list']
        zz_list = ss['zz_list']
        W_list_old = params['W_list']

        # Update components param
        components = np.array([r/n_examples for r in r_list])

        # Update mean / Sigma params
        mu_list = []
        W_list = []
        Psi_list = []
        for r, W, x, xx, xz, zx, z, zz in zip(r_list, W_list_old, x_list,
                                              xx_list, xz_list, zx_list,
                                              z_list, zz_list):
            # mu
            resid = x - W @ z
            mu = resid / r
            mu_list.append(mu)

            # W
            try:
                W = np.linalg.solve(zz, xz.T).T
            except np.linalg.linalg.LinAlgError:
                if self.robust:
                    zz_cond = zz + self.SMALL*np.eye(self.latent_dim)
                    W = np.linalg.solve(zz_cond, xz.T).T
                else:
                    raise np.linalg.linalg.LinAlgError(self.error_msg)
            W_list.append(W)

            # Psi
            Psi = np.diag(np.diag(xx - W @ zx)) / r
            Psi_list.append(Psi)

        # Store params in dictionary
        params = {'W_list': W_list,
                  'Psi_list': Psi_list,
                  'mu_list': mu_list,
                  'components': components}
        return params

    def sample(self, n_samples=1, noisy=True):
        """Sample from fitted model.

        Sample from fitted model by first sampling from latent space
        (spherical Gaussian) then transforming into data space using learned
        parameters. Noise can then be added optionally.

        Parameters
        ----------
        nSamples : int
            Number of samples to generate
        noisy : bool
            Option to add noise to samples (default = True)

        Returns
        -------
        dataSamples : array [nSamples, dataDim]
            Collection of samples in data space.
        """
        if not self.isFitted:
            print("Model is not yet fitted. First use fit to learn the " +
                  "model params.")
        else:
            components = self.params['components']
            mu_list = self.params['mu_list']
            Sigma_list = self._params_to_Sigma(self.params, noisy=noisy)
            components_cumsum = np.cumsum(components)
            samples = np.zeros([n_samples, self.data_dim])
            for n in range(n_samples):
                r = np.random.rand(1)
                z = np.argmin(r > components_cumsum)
                samples[n] = rd.multivariate_normal(mu_list[z], Sigma_list[z])
            return samples

    def _params_to_Sigma(self, params, noisy=True):
        W_list = params['W_list']
        Psi_list = params['Psi_list']
        if noisy:
            Sigma_list = [W @ W.T + Psi for W, Psi in zip(W_list, Psi_list)]
        else:
            Sigma_list = [W @ W.T for W in W_list]
        return Sigma_list

    def reconstruct(self, Z, component, noisy=False):
        """Sample from fitted model.

        Sample from fitted model by first sampling from latent space
        (spherical Gaussian) then transforming into data space using learned
        parameters. Noise can then be added optionally.

        Parameters
        ----------
        nSamples : int
            Number of samples to generate
        noisy : bool
            Option to add noise to samples (default = True)

        Returns
        -------
        dataSamples : array [nSamples, dataDim]
            Collection of samples in data space.
        """
        if not self.isFitted:
            print("Model is not yet fitted. First use fit to learn the " +
                  "model params.")
        else:
            mu = self.params['mu_list'][component]
            W = self.params['W_list'][component]
            Psi = self.params['Psi_list'][component]
            reconstructions = Z @ W.T + mu
            if noisy:
                noise = np.random.multivariate_normal(
                            np.zeros(self.data_dim), Psi, Z.shape[0]
                        )
                reconstructions = reconstructions + noise
            return reconstructions
