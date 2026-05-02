"""multi-agent-council — 7-phase structured deliberation protocol for multi-agent AI systems."""
__version__ = "1.0.0"

from multi_agent_council.council import (
    CLIBackend,
    SubprocessBackend,
    DryRunBackend,
    CouncilResult,
    Council,
    HeadlessCouncil,
)

__all__ = [
    "CLIBackend",
    "SubprocessBackend",
    "DryRunBackend",
    "CouncilResult",
    "Council",
    "HeadlessCouncil",
]
