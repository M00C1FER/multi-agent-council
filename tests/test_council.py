"""Smoke tests for multi-agent-council."""
import pytest


def test_import():
    from multi_agent_council import Council, DryRunBackend, CLIBackend
    assert Council
    assert DryRunBackend
    assert CLIBackend


def test_dry_run_completes():
    from multi_agent_council import Council, DryRunBackend
    council = Council(backends=[DryRunBackend("a"), DryRunBackend("b")])
    result = council.deliberate("Test topic", dry_run=True)
    assert result.topic == "Test topic"
    assert result.confidence >= 0.0
    assert len(result.phase_outputs) == 7


def test_seven_phases():
    from multi_agent_council import Council, DryRunBackend
    council = Council(backends=[DryRunBackend("x")])
    result = council.deliberate("phase test", dry_run=True)
    expected = {"BRIEF", "RECON", "INTEL", "WARGAME", "REFINE", "COUNCIL", "DEBRIEF"}
    assert set(result.phase_outputs.keys()) == expected
