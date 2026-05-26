from cybernetics.regime import MarketRegime


def test_regime_transition_tracker_requires_consecutive_dwell_before_switch():
    from cybernetics.regime_state import RegimeTransitionTracker

    tracker = RegimeTransitionTracker(min_dwell=3)

    first = tracker.apply(MarketRegime.BULL, score=72.0, as_of="2026-05-20")
    assert first.confirmed is MarketRegime.BULL
    assert first.raw is MarketRegime.BULL
    assert first.pending is None
    assert first.pending_count == 0

    first_bear = tracker.apply(MarketRegime.BEAR, score=35.0, as_of="2026-05-21")
    assert first_bear.confirmed is MarketRegime.BULL
    assert first_bear.raw is MarketRegime.BEAR
    assert first_bear.pending is MarketRegime.BEAR
    assert first_bear.pending_count == 1
    assert first_bear.confirmed_changed is False

    reset_pending = tracker.apply(MarketRegime.SIDEWAYS, score=52.0, as_of="2026-05-22")
    assert reset_pending.confirmed is MarketRegime.BULL
    assert reset_pending.pending is MarketRegime.SIDEWAYS
    assert reset_pending.pending_count == 1

    tracker.apply(MarketRegime.BEAR, score=35.0, as_of="2026-05-23")
    almost = tracker.apply(MarketRegime.BEAR, score=34.0, as_of="2026-05-24")
    assert almost.confirmed is MarketRegime.BULL
    assert almost.pending_count == 2

    switched = tracker.apply(MarketRegime.BEAR, score=33.0, as_of="2026-05-25")
    assert switched.confirmed is MarketRegime.BEAR
    assert switched.pending is None
    assert switched.pending_count == 0
    assert switched.confirmed_changed is True


def test_regime_transition_tracker_bypasses_unknown_and_clears_pending():
    from cybernetics.regime_state import RegimeTransitionTracker

    tracker = RegimeTransitionTracker(min_dwell=3)
    tracker.apply(MarketRegime.BULL, score=70.0)
    tracker.apply(MarketRegime.BEAR, score=35.0)

    unknown = tracker.apply(MarketRegime.UNKNOWN, score=50.0)

    assert unknown.confirmed is MarketRegime.UNKNOWN
    assert unknown.raw is MarketRegime.UNKNOWN
    assert unknown.pending is None
    assert unknown.pending_count == 0


def test_regime_transition_tracker_counts_unique_observations_not_refreshes():
    from cybernetics.regime_state import RegimeTransitionTracker

    tracker = RegimeTransitionTracker(min_dwell=3)
    tracker.apply(MarketRegime.BULL, score=72.0, as_of="2026-05-20")
    tracker.apply(MarketRegime.BEAR, score=35.0, as_of="2026-05-21")

    duplicate_refresh = tracker.apply(MarketRegime.BEAR, score=35.0, as_of="2026-05-21")
    assert duplicate_refresh.confirmed is MarketRegime.BULL
    assert duplicate_refresh.pending_count == 1

    tracker.apply(MarketRegime.BEAR, score=34.0, as_of="2026-05-22")
    switched = tracker.apply(MarketRegime.BEAR, score=33.0, as_of="2026-05-23")

    assert switched.confirmed is MarketRegime.BEAR
    assert switched.pending_count == 0


def test_regime_transition_tracker_persists_pending_state(tmp_path):
    from cybernetics.regime_state import RegimeTransitionTracker

    state_path = tmp_path / "market_regime_state.json"
    tracker = RegimeTransitionTracker(min_dwell=3, state_path=state_path)
    tracker.apply(MarketRegime.BULL, score=72.0, as_of="2026-05-20")
    tracker.apply(MarketRegime.BEAR, score=35.0, as_of="2026-05-21")

    restored = RegimeTransitionTracker(min_dwell=3, state_path=state_path)
    continued = restored.apply(MarketRegime.BEAR, score=34.0, as_of="2026-05-22")
    assert continued.confirmed is MarketRegime.BULL
    assert continued.pending is MarketRegime.BEAR
    assert continued.pending_count == 2

    switched = restored.apply(MarketRegime.BEAR, score=33.0, as_of="2026-05-23")
    assert switched.confirmed is MarketRegime.BEAR
    assert switched.pending is None
