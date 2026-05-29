"""Student-t Hidden Markov Model for market regime detection.

Implements the EM algorithm for HMMs with Student-t emission distributions,
which better handle the fat tails typical of financial returns compared to
Gaussian emissions.

The model learns K hidden states from an observation sequence of D-dimensional
feature vectors.  For market regime detection we use K=3 (bull, sideways, bear).
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy import special, linalg

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HMMConfig:
    """Hyperparameters for the Student-t HMM."""
    n_states: int = 3
    max_iter: int = 100
    tol: float = 1e-4
    n_init: int = 5
    min_df: float = 3.0
    max_df: float = 30.0
    random_seed: int = 42
    reg_covar: float = 1e-6  # regularisation for covariance matrices

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class HMMResult:
    """Output of a fitted Student-t HMM."""
    state_probs: np.ndarray       # (n_samples, K) posterior state probabilities
    viterbi_states: np.ndarray    # (n_samples,) most-likely state sequence
    means: np.ndarray             # (K, D) emission means
    covars: np.ndarray            # (K, D, D) emission covariances
    df: np.ndarray                # (K,) Student-t degrees of freedom
    transmat: np.ndarray          # (K, K) transition matrix
    startprob: np.ndarray         # (K,) initial state distribution
    log_likelihood: float
    n_iter: int
    aic: float
    bic: float
    n_samples: int
    n_features: int
    config: HMMConfig = field(default_factory=HMMConfig)

    def to_dict(self) -> dict:
        """Serialise to JSON-compatible dict (arrays → lists)."""
        d = {
            "means": self.means.tolist(),
            "covars": self.covars.tolist(),
            "df": self.df.tolist(),
            "transmat": self.transmat.tolist(),
            "startprob": self.startprob.tolist(),
            "log_likelihood": self.log_likelihood,
            "n_iter": self.n_iter,
            "aic": self.aic,
            "bic": self.bic,
            "n_samples": self.n_samples,
            "n_features": self.n_features,
            "config": self.config.to_dict(),
        }
        return d


# ---------------------------------------------------------------------------
# Student-t log-density
# ---------------------------------------------------------------------------

def _student_t_logprob(
    X: np.ndarray,       # (N, D)
    mu: np.ndarray,      # (D,)
    sigma: np.ndarray,   # (D, D)
    df: float,
) -> np.ndarray:
    """Log-density of multivariate Student-t distribution.

    Returns array of shape (N,).
    """
    D = X.shape[1]
    diff = X - mu  # (N, D)

    # Cholesky decomposition for numerical stability
    try:
        L = linalg.cholesky(sigma, lower=True)
    except linalg.LinAlgError:
        # Add regularisation and retry
        sigma_reg = sigma + np.eye(D) * 1e-4
        L = linalg.cholesky(sigma_reg, lower=True)

    # Solve L @ y = diff^T  →  y = L^{-1} @ diff^T
    solve = linalg.solve_triangular(L, diff.T, lower=True)  # (D, N)
    mahal = np.sum(solve ** 2, axis=0)  # (N,)

    # Log-density: log Γ((ν+D)/2) - log Γ(ν/2) - D/2 log(νπ) - 1/2 log|Σ| - (ν+D)/2 log(1 + mahal/ν)
    log_norm = (
        special.gammaln((df + D) / 2)
        - special.gammaln(df / 2)
        - (D / 2) * np.log(df * np.pi)
        - np.sum(np.log(np.diag(L)))  # log|Σ|^{1/2} = sum log diag(L)
    )
    log_kernel = -((df + D) / 2) * np.log(1 + mahal / df)

    return log_norm + log_kernel


# ---------------------------------------------------------------------------
# EM algorithm helpers
# ---------------------------------------------------------------------------

def _init_params(
    X: np.ndarray,
    K: int,
    rng: np.random.Generator,
    min_df: float = 3.0,
    max_df: float = 30.0,
) -> dict:
    """Initialise HMM parameters via K-means-like splitting."""
    N, D = X.shape

    # Use quantile-based initialisation for robustness
    order = np.argsort(X[:, 0])  # sort by first feature
    assignments = np.zeros(N, dtype=int)
    for i in range(N):
        assignments[i] = int(i * K / N)

    means = np.zeros((K, D))
    covars = np.zeros((K, D, D))
    df_arr = np.full(K, 5.0)

    for k in range(K):
        mask = assignments == k
        if mask.sum() < D + 1:
            # Not enough points; use global stats
            means[k] = X.mean(axis=0)
            covars[k] = np.cov(X.T) + np.eye(D) * 1e-4
        else:
            Xk = X[mask]
            means[k] = Xk.mean(axis=0)
            covars[k] = np.cov(Xk.T) + np.eye(D) * 1e-4

    # Transition matrix: near-identity with small off-diagonal
    transmat = np.full((K, K), 0.05 / (K - 1))
    np.fill_diagonal(transmat, 0.95)

    startprob = np.ones(K) / K

    return {
        "means": means,
        "covars": covars,
        "df": df_arr,
        "transmat": transmat,
        "startprob": startprob,
    }


def _e_step(
    X: np.ndarray,
    params: dict,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """Forward-backward E-step.

    Returns:
        gamma: (N, K) posterior state probabilities
        xi: (N-1, K, K) pairwise posterior
        logprob: total log-likelihood
        log_alpha: (N, K) log forward variables
    """
    N, D = X.shape
    K = params["means"].shape[0]
    means = params["means"]
    covars = params["covars"]
    df_arr = params["df"]
    transmat = params["transmat"]
    startprob = params["startprob"]

    # Compute log emission probabilities: (N, K)
    log_emit = np.zeros((N, K))
    for k in range(K):
        log_emit[:, k] = _student_t_logprob(X, means[k], covars[k], df_arr[k])

    # Forward pass (log domain)
    log_alpha = np.full((N, K), -np.inf)
    log_startprob = np.log(startprob + 1e-300)
    log_transmat = np.log(transmat + 1e-300)

    log_alpha[0] = log_startprob + log_emit[0]

    for t in range(1, N):
        for k in range(K):
            # log sum_j alpha[t-1,j] * transmat[j,k]
            log_alpha[t, k] = (
                special.logsumexp(log_alpha[t - 1] + log_transmat[:, k])
                + log_emit[t, k]
            )

    # Backward pass
    log_beta = np.full((N, K), -np.inf)
    # log_beta[N-1] = 0  (already -inf, set to 0)
    log_beta[N - 1] = 0.0

    for t in range(N - 2, -1, -1):
        for k in range(K):
            log_beta[t, k] = special.logsumexp(
                log_transmat[k, :] + log_emit[t + 1] + log_beta[t + 1]
            )

    # Posterior: gamma[t, k] = alpha[t,k] * beta[t,k] / sum_j alpha[t,j] * beta[t,j]
    log_gamma = log_alpha + log_beta
    log_gamma -= special.logsumexp(log_gamma, axis=1, keepdims=True)
    gamma = np.exp(log_gamma)

    # Pairwise: xi[t, i, j] = alpha[t,i] * transmat[i,j] * emit[t+1,j] * beta[t+1,j] / evidence
    xi = np.zeros((N - 1, K, K))
    for t in range(N - 1):
        log_xi_t = (
            log_alpha[t, :, None]
            + log_transmat
            + log_emit[t + 1, None, :]
            + log_beta[t + 1, None, :]
        )
        log_xi_t -= special.logsumexp(log_xi_t)
        xi[t] = np.exp(log_xi_t)

    logprob = special.logsumexp(log_alpha[-1])

    return gamma, xi, logprob, log_alpha


def _m_step(
    X: np.ndarray,
    gamma: np.ndarray,
    xi: np.ndarray,
    params: dict,
    min_df: float = 3.0,
    max_df: float = 30.0,
    reg_covar: float = 1e-6,
) -> dict:
    """M-step: update parameters from responsibilities."""
    N, D = X.shape
    K = gamma.shape[1]

    # Initial state
    startprob = gamma[0] / gamma[0].sum()

    # Transition matrix
    transmat = xi.sum(axis=0)  # (K, K)
    row_sums = transmat.sum(axis=1, keepdims=True)
    row_sums[row_sums == 0] = 1
    transmat = transmat / row_sums

    means = np.zeros((K, D))
    covars = np.zeros((K, D, D))
    df_arr = np.zeros(K)

    for k in range(K):
        gk = gamma[:, k]  # (N,)
        Nk = gk.sum()
        if Nk < 1e-10:
            means[k] = params["means"][k]
            covars[k] = params["covars"][k]
            df_arr[k] = params["df"][k]
            continue

        # Effective weights for Student-t: w[i,k] = (nu + D) / (nu + delta_ik)
        old_df = params["df"][k]
        old_mean = params["means"][k]
        old_covar = params["covars"][k]

        diff = X - old_mean  # (N, D)
        try:
            L = linalg.cholesky(old_covar, lower=True)
            solve = linalg.solve_triangular(L, diff.T, lower=True)
            mahal = np.sum(solve ** 2, axis=0)
        except linalg.LinAlgError:
            mahal = np.sum(diff ** 2, axis=0) / (np.trace(old_covar) / D + 1e-10)

        w = (old_df + D) / (old_df + mahal)  # (N,)
        gw = gk * w  # (N,)

        Nk_w = gw.sum()
        if Nk_w < 1e-10:
            Nk_w = 1e-10

        # Weighted mean
        means[k] = (gw[:, None] * X).sum(axis=0) / Nk_w

        # Weighted covariance
        diff_new = X - means[k]
        covars[k] = (
            (gw[:, None, None] * (diff_new[:, :, None] * diff_new[:, None, :])).sum(axis=0)
            / Nk_w
            + np.eye(D) * reg_covar
        )

        # Update degrees of freedom via Newton's method
        df_arr[k] = _update_df(gk, w, old_df, min_df, max_df)

    return {
        "means": means,
        "covars": covars,
        "df": df_arr,
        "transmat": transmat,
        "startprob": startprob,
    }


def _update_df(
    gk: np.ndarray,
    w: np.ndarray,
    current_df: float,
    min_df: float,
    max_df: float,
    max_iter: int = 20,
) -> float:
    """Update Student-t degrees of freedom via Newton's method.

    Solves: d/dν [ Σ_i γ_ik * (log Γ((ν+D)/2) - log Γ(ν/2) - ν/2 * log(ν) + ν/2 * w_i ) ] = 0
    """
    nu = current_df
    D = 1  # effective dimension for this update (simplified)
    Nk_eff = gk.sum()
    if Nk_eff < 1e-10:
        return current_df

    weighted_log_w = (gk * np.log(w + 1e-300)).sum() / Nk_eff

    for _ in range(max_iter):
        half_nu = nu / 2
        half_nu_D = (nu + D) / 2

        # Gradient
        grad = (
            Nk_eff * (special.digamma(half_nu_D) - special.digamma(half_nu))
            + Nk_eff * (1 - D / nu - weighted_log_w) / 2  # simplified
        )

        # Hessian (approximate)
        hess = (
            Nk_eff * (special.polygamma(1, half_nu_D) - special.polygamma(1, half_nu)) / 4
            + Nk_eff * D / (2 * nu ** 2)
        )

        if abs(hess) < 1e-15:
            break

        step = grad / hess
        nu_new = nu - step
        nu_new = max(min_df, min(max_df, nu_new))

        if abs(nu_new - nu) < 1e-4:
            break
        nu = nu_new

    return nu


def _compute_loglikelihood(
    X: np.ndarray,
    params: dict,
) -> float:
    """Compute the marginal log-likelihood of the data."""
    N, D = X.shape
    K = params["means"].shape[0]

    log_emit = np.zeros((N, K))
    for k in range(K):
        log_emit[:, k] = _student_t_logprob(X, params["means"][k], params["covars"][k], params["df"][k])

    log_startprob = np.log(params["startprob"] + 1e-300)
    log_transmat = np.log(params["transmat"] + 1e-300)

    log_alpha = np.full((N, K), -np.inf)
    log_alpha[0] = log_startprob + log_emit[0]

    for t in range(1, N):
        for k in range(K):
            log_alpha[t, k] = (
                special.logsumexp(log_alpha[t - 1] + log_transmat[:, k])
                + log_emit[t, k]
            )

    return float(special.logsumexp(log_alpha[-1]))


# ---------------------------------------------------------------------------
# Viterbi decoding
# ---------------------------------------------------------------------------

def _viterbi(
    X: np.ndarray,
    params: dict,
) -> np.ndarray:
    """Viterbi algorithm: find most-likely state sequence."""
    N, D = X.shape
    K = params["means"].shape[0]

    log_emit = np.zeros((N, K))
    for k in range(K):
        log_emit[:, k] = _student_t_logprob(X, params["means"][k], params["covars"][k], params["df"][k])

    log_startprob = np.log(params["startprob"] + 1e-300)
    log_transmat = np.log(params["transmat"] + 1e-300)

    # Forward pass
    delta = np.full((N, K), -np.inf)
    psi = np.zeros((N, K), dtype=int)
    delta[0] = log_startprob + log_emit[0]

    for t in range(1, N):
        for k in range(K):
            scores = delta[t - 1] + log_transmat[:, k]
            psi[t, k] = np.argmax(scores)
            delta[t, k] = scores[psi[t, k]] + log_emit[t, k]

    # Backtrack
    states = np.zeros(N, dtype=int)
    states[N - 1] = np.argmax(delta[N - 1])
    for t in range(N - 2, -1, -1):
        states[t] = psi[t + 1, states[t + 1]]

    return states


# ---------------------------------------------------------------------------
# State alignment
# ---------------------------------------------------------------------------

def align_states(result: HMMResult, X: np.ndarray | None = None) -> HMMResult:
    """Align state labels so that:
    - State with highest mean return_1d → index 0 (bull)
    - State with lowest mean return_1d  → index 2 (bear)
    - Middle                           → index 1 (sideways)

    Uses a composite score of return_1d (feature 0) and realized_vol_20d (feature 1)
    for more robust alignment: high return + low vol = bull, low return + high vol = bear.
    """
    K = result.means.shape[0]
    if K != 3:
        return result  # only align for 3-state models

    # Composite alignment score: return_1d mean - 0.3 * vol mean
    # Bull: high return, low vol → high score
    # Bear: low return, high vol → low score
    return_means = result.means[:, 0]  # return_1d
    vol_means = result.means[:, 1] if result.means.shape[1] > 1 else np.zeros(K)
    alignment_score = return_means - 0.3 * vol_means
    order = np.argsort(-alignment_score)  # descending: [bull_idx, sideways_idx, bear_idx]

    if np.array_equal(order, [0, 1, 2]):
        return result  # already aligned

    # Reorder everything
    means = result.means[order]
    covars = result.covars[order]
    df_arr = result.df[order]
    transmat = result.transmat[np.ix_(order, order)]
    startprob = result.startprob[order]
    state_probs = result.state_probs[:, order]
    viterbi_states = np.array([order[s] for s in result.viterbi_states])

    return HMMResult(
        state_probs=state_probs,
        viterbi_states=viterbi_states,
        means=means,
        covars=covars,
        df=df_arr,
        transmat=transmat,
        startprob=startprob,
        log_likelihood=result.log_likelihood,
        n_iter=result.n_iter,
        aic=result.aic,
        bic=result.bic,
        n_samples=result.n_samples,
        n_features=result.n_features,
        config=result.config,
    )


# ---------------------------------------------------------------------------
# Main model class
# ---------------------------------------------------------------------------

class StudentTHMM:
    """Student-t Hidden Markov Model with EM training."""

    def __init__(self, config: HMMConfig = HMMConfig()):
        self.config = config
        self._params: dict | None = None
        self._result: HMMResult | None = None

    def fit(self, X: np.ndarray) -> HMMResult:
        """Fit the model using multiple random initialisations.

        Parameters
        ----------
        X : observation matrix, shape (N, D)

        Returns
        -------
        HMMResult with the best log-likelihood across initialisations.
        """
        X = np.asarray(X, dtype=np.float64)
        if X.ndim == 1:
            X = X.reshape(-1, 1)

        N, D = X.shape
        K = self.config.n_states
        rng = np.random.default_rng(self.config.random_seed)

        best_result = None
        best_ll = -np.inf

        for init_idx in range(self.config.n_init):
            try:
                result = self._fit_single(X, K, rng)
                if result.log_likelihood > best_ll:
                    best_ll = result.log_likelihood
                    best_result = result
            except Exception as e:
                log.warning(f"HMM init {init_idx} failed: {e}")
                continue

        if best_result is None:
            raise RuntimeError("All HMM initialisations failed")

        self._params = {
            "means": best_result.means,
            "covars": best_result.covars,
            "df": best_result.df,
            "transmat": best_result.transmat,
            "startprob": best_result.startprob,
        }
        self._result = best_result

        # Align states
        self._result = align_states(self._result, X)
        self._params = {
            "means": self._result.means,
            "covars": self._result.covars,
            "df": self._result.df,
            "transmat": self._result.transmat,
            "startprob": self._result.startprob,
        }

        return self._result

    def _fit_single(self, X: np.ndarray, K: int, rng: np.random.Generator) -> HMMResult:
        """Single EM run from one initialisation."""
        N, D = X.shape
        params = _init_params(X, K, rng, self.config.min_df, self.config.max_df)

        prev_ll = -np.inf
        n_iter = 0

        for iteration in range(self.config.max_iter):
            # E-step
            gamma, xi, logprob, _ = _e_step(X, params)

            # M-step
            params = _m_step(
                X, gamma, xi, params,
                min_df=self.config.min_df,
                max_df=self.config.max_df,
                reg_covar=self.config.reg_covar,
            )

            n_iter = iteration + 1

            if abs(logprob - prev_ll) < self.config.tol:
                break
            prev_ll = logprob

        # Final E-step for gamma
        gamma, xi, logprob, _ = _e_step(X, params)
        viterbi = _viterbi(X, params)

        # Information criteria
        n_params = K * D + K * D * (D + 1) // 2 + K + K * K + K - 1 + K  # means + covars + df + transmat + startprob
        aic = -2 * logprob + 2 * n_params
        bic = -2 * logprob + n_params * np.log(N)

        return HMMResult(
            state_probs=gamma,
            viterbi_states=viterbi,
            means=params["means"],
            covars=params["covars"],
            df=params["df"],
            transmat=params["transmat"],
            startprob=params["startprob"],
            log_likelihood=logprob,
            n_iter=n_iter,
            aic=aic,
            bic=bic,
            n_samples=N,
            n_features=D,
            config=self.config,
        )

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Compute posterior state probabilities for new observations.

        Returns
        -------
        np.ndarray of shape (N, K)
        """
        if self._params is None:
            raise RuntimeError("Model not fitted. Call fit() first.")

        X = np.asarray(X, dtype=np.float64)
        if X.ndim == 1:
            X = X.reshape(-1, 1)

        gamma, _, _, _ = _e_step(X, self._params)
        return gamma

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Viterbi decoding of most-likely state sequence."""
        if self._params is None:
            raise RuntimeError("Model not fitted. Call fit() first.")

        X = np.asarray(X, dtype=np.float64)
        if X.ndim == 1:
            X = X.reshape(-1, 1)

        return _viterbi(X, self._params)

    def score(self, X: np.ndarray) -> float:
        """Compute marginal log-likelihood."""
        if self._params is None:
            raise RuntimeError("Model not fitted. Call fit() first.")

        X = np.asarray(X, dtype=np.float64)
        if X.ndim == 1:
            X = X.reshape(-1, 1)

        return _compute_loglikelihood(X, self._params)

    @property
    def result(self) -> HMMResult | None:
        return self._result

    @property
    def is_fitted(self) -> bool:
        return self._params is not None


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def save_hmm_model(result: HMMResult, path: str | Path) -> None:
    """Save model parameters to disk."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)

    # Save arrays
    np.savez(
        path / "params.npz",
        means=result.means,
        covars=result.covars,
        df=result.df,
        transmat=result.transmat,
        startprob=result.startprob,
    )

    # Save metadata
    meta = {
        "log_likelihood": result.log_likelihood,
        "n_iter": result.n_iter,
        "aic": result.aic,
        "bic": result.bic,
        "n_samples": result.n_samples,
        "n_features": result.n_features,
        "config": result.config.to_dict(),
    }
    (path / "meta.json").write_text(json.dumps(meta, indent=2))


def load_hmm_model(path: str | Path, config: HMMConfig | None = None) -> HMMResult:
    """Load model parameters from disk."""
    path = Path(path)

    data = np.load(path / "params.npz")
    meta = json.loads((path / "meta.json").read_text())

    cfg = config or HMMConfig(**meta.get("config", {}))

    return HMMResult(
        state_probs=np.array([]),  # not persisted; recompute via predict_proba
        viterbi_states=np.array([]),
        means=data["means"],
        covars=data["covars"],
        df=data["df"],
        transmat=data["transmat"],
        startprob=data["startprob"],
        log_likelihood=meta["log_likelihood"],
        n_iter=meta["n_iter"],
        aic=meta["aic"],
        bic=meta["bic"],
        n_samples=meta["n_samples"],
        n_features=meta["n_features"],
        config=cfg,
    )
