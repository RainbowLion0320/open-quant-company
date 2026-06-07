import numpy as np
import pytest

from cybernetics.hmm import HMMConfig, HMMResult, align_states


def test_align_states_remaps_viterbi_states_with_inverse_mapping():
    result = HMMResult(
        state_probs=np.array([
            [0.10, 0.70, 0.20],
            [0.20, 0.20, 0.60],
        ]),
        viterbi_states=np.array([0, 1, 2, 1]),
        means=np.array([
            [0.10, 0.05],
            [-0.20, 0.60],
            [0.30, 0.10],
        ]),
        covars=np.array([np.eye(2), np.eye(2) * 2, np.eye(2) * 3]),
        df=np.array([8.0, 5.0, 12.0]),
        transmat=np.array([
            [0.80, 0.10, 0.10],
            [0.20, 0.70, 0.10],
            [0.15, 0.15, 0.70],
        ]),
        startprob=np.array([0.20, 0.30, 0.50]),
        log_likelihood=-12.0,
        n_iter=8,
        aic=30.0,
        bic=35.0,
        n_samples=4,
        n_features=2,
        config=HMMConfig(),
    )

    aligned = align_states(result)

    assert aligned.means[:, 0].tolist() == [0.30, 0.10, -0.20]
    assert aligned.state_probs.tolist() == [[0.20, 0.10, 0.70], [0.60, 0.20, 0.20]]
    assert aligned.viterbi_states.tolist() == [1, 2, 0, 2]


def test_save_load_hmm_model_preserves_pca_preprocessor(tmp_path):
    from sklearn.decomposition import PCA

    from cybernetics.hmm import apply_hmm_preprocessor, load_hmm_model, save_hmm_model

    raw = np.array([
        [1.0, 2.0, 3.0],
        [2.0, 3.0, 5.0],
        [3.0, 5.0, 8.0],
        [4.0, 7.0, 13.0],
    ])
    pca = PCA(n_components=2, whiten=True).fit(raw)
    result = HMMResult(
        state_probs=np.zeros((4, 3)),
        viterbi_states=np.zeros(4, dtype=int),
        means=np.zeros((3, 2)),
        covars=np.array([np.eye(2), np.eye(2), np.eye(2)]),
        df=np.array([8.0, 8.0, 8.0]),
        transmat=np.eye(3),
        startprob=np.array([1.0, 0.0, 0.0]),
        log_likelihood=-12.0,
        n_iter=3,
        aic=30.0,
        bic=35.0,
        n_samples=4,
        n_features=2,
        config=HMMConfig(),
    )

    save_hmm_model(result, tmp_path, preprocessor=pca)
    loaded = load_hmm_model(tmp_path)

    transformed = apply_hmm_preprocessor(raw[:1], loaded.preprocessor)

    assert loaded.preprocessor["kind"] == "pca"
    assert transformed.shape == (1, 2)
    assert transformed == pytest.approx(pca.transform(raw[:1]))
