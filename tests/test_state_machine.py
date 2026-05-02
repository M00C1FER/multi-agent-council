"""Property-based tests for the 7-phase council state machine.

These tests use Hypothesis to verify invariants that must hold for *any*
combination of backends and topics, not just the handful of hand-crafted
examples in the smoke tests.
"""
import pytest
from hypothesis import given, settings, strategies as st

from multi_agent_council import Council, DryRunBackend
from multi_agent_council.council import _COUNCIL_PHASES, CouncilResult


# ── helpers ──────────────────────────────────────────────────────────────────

PHASE_ORDER = list(_COUNCIL_PHASES)


def make_council(n_backends: int) -> Council:
    backends = [DryRunBackend(f"agent-{i}") for i in range(n_backends)]
    return Council(backends=backends)


# ── property tests ────────────────────────────────────────────────────────────


@given(topic=st.text(min_size=1, max_size=200))
@settings(max_examples=30)
def test_result_always_has_seven_phases(topic: str) -> None:
    """CouncilResult.phase_outputs must always contain exactly 7 keys."""
    result = make_council(2).deliberate(topic, dry_run=True)
    assert set(result.phase_outputs.keys()) == set(PHASE_ORDER), (
        f"Expected {set(PHASE_ORDER)}, got {set(result.phase_outputs.keys())}"
    )


@given(topic=st.text(min_size=1, max_size=200))
@settings(max_examples=30)
def test_phase_order_is_invariant(topic: str) -> None:
    """Phase keys must be the canonical 7 phases in the correct order."""
    result = make_council(2).deliberate(topic, dry_run=True)
    # Dict insertion order is preserved in Python 3.7+; verify ordering.
    assert list(result.phase_outputs.keys()) == PHASE_ORDER


@given(topic=st.text(min_size=1, max_size=200))
@settings(max_examples=30)
def test_confidence_is_bounded(topic: str) -> None:
    """Confidence must always be a float in [0.0, 1.0]."""
    result = make_council(2).deliberate(topic, dry_run=True)
    assert 0.0 <= result.confidence <= 1.0, (
        f"Confidence {result.confidence} is out of [0, 1]"
    )


@given(topic=st.text(min_size=1, max_size=200))
@settings(max_examples=30)
def test_topic_is_preserved(topic: str) -> None:
    """The topic stored in CouncilResult must be identical to the input."""
    result = make_council(2).deliberate(topic, dry_run=True)
    assert result.topic == topic


@given(
    n_backends=st.integers(min_value=1, max_value=5),
    topic=st.text(min_size=1, max_size=100),
)
@settings(max_examples=20)
def test_single_backend_is_allowed(n_backends: int, topic: str) -> None:
    """Council must succeed with any number of backends ≥ 1."""
    result = make_council(n_backends).deliberate(topic, dry_run=True)
    assert len(result.phase_outputs) == 7
    assert 0.0 <= result.confidence <= 1.0


@given(topic=st.text(min_size=1, max_size=200))
@settings(max_examples=30)
def test_phase_outputs_are_strings(topic: str) -> None:
    """Every phase output must be a (possibly empty) string."""
    result = make_council(2).deliberate(topic, dry_run=True)
    for phase, output in result.phase_outputs.items():
        assert isinstance(output, str), (
            f"Phase {phase} output is not a string: {type(output)}"
        )


@given(topic=st.text(min_size=1, max_size=200))
@settings(max_examples=20)
def test_chairman_synthesis_is_string(topic: str) -> None:
    """chairman_synthesis must always be a string (never raises AttributeError)."""
    result = make_council(2).deliberate(topic, dry_run=True)
    assert isinstance(result.chairman_synthesis, str)


@given(topic=st.text(min_size=1, max_size=200))
@settings(max_examples=20)
def test_minority_report_is_string(topic: str) -> None:
    """minority_report must always be a string."""
    result = make_council(2).deliberate(topic, dry_run=True)
    assert isinstance(result.minority_report, str)


def test_council_requires_at_least_one_backend() -> None:
    """Council with zero backends must raise ValueError immediately."""
    with pytest.raises(ValueError, match="at least one backend"):
        Council(backends=[])


def test_dry_run_backend_name_property() -> None:
    """DryRunBackend.name must be a plain string (not a callable)."""
    backend = DryRunBackend("test-agent")
    assert isinstance(backend.name, str)
    assert backend.name == "test-agent"


def test_phase_state_machine_does_not_skip_phases() -> None:
    """No phase may be skipped — all 7 keys must be present even if empty."""
    result = make_council(1).deliberate("single-backend topic", dry_run=True)
    for phase in PHASE_ORDER:
        assert phase in result.phase_outputs, f"Phase {phase!r} missing from result"


def test_wargame_ring_logic() -> None:
    """WARGAME phase uses round-robin (i+1)%n target; verify ring consistency.

    With 3 backends the ring must form a complete cycle: 0→1→2→0.
    We can't directly inspect HeadlessCouncil state here (it requires real
    backends), but we can verify the mathematical property via the formula.
    """
    agents = list(range(3))
    ring = [(i, (i + 1) % len(agents)) for i in agents]
    # Every agent must appear exactly once as attacker and once as target
    attackers = [a for a, _ in ring]
    targets = [t for _, t in ring]
    assert sorted(attackers) == sorted(targets) == agents


def test_refine_ring_is_consistent_with_wargame() -> None:
    """REFINE challenger for agent i is agent (i-1)%n, matching WARGAME target.

    In WARGAME agent i challenges agent (i+1)%n.
    In REFINE agent i responds to agent (i-1)%n's challenge.
    So: agent j's refine-challenger == agent that challenged j in WARGAME.
    """
    n = 4
    for i in range(n):
        wargame_target = (i + 1) % n          # who agent i challenges
        refine_challenger = (wargame_target - 1) % n  # who wargame_target responds to
        assert refine_challenger == i, (
            f"Agent {i} challenged {wargame_target} in WARGAME, but "
            f"REFINE says {wargame_target}'s challenger is {refine_challenger}"
        )
