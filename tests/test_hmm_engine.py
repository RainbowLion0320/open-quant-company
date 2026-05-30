import numpy as np

from cybernetics.hmm_engine import HMMConfig, HMMResult, align_states


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
