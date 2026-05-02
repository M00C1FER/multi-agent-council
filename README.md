# Multi-Agent Council

> Structured 7-phase AI think-tank deliberation — BRIEF, RECON, INTEL, WARGAME, REFINE, COUNCIL, DEBRIEF.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org)
[![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20WSL%20%7C%20Termux-lightgrey)](install.sh)

## What It Does

Simple "ask multiple AIs" approaches produce redundant output. Multi-Agent Council forces genuine divergence through adversarial phase design: each AI CLI researches independently (no cross-pollination), then shares findings, then challenges peers, then refines under pressure. A ConsensusEngine vote closes each session with a chairman synthesis and mandatory minority report.

**The 7 phases:**

| Phase | Purpose |
|-------|---------|
| **BRIEF** | Define mission, assign roles, set success criteria |
| **RECON** | Each agent researches independently (no sharing) |
| **INTEL** | Blackboard sharing — all findings visible to all |
| **WARGAME** | Round-robin adversarial challenges |
| **REFINE** | Evidence-based position updates (Delphi) |
| **COUNCIL** | Formal vote + chairman synthesis |
| **DEBRIEF** | AAR, confidence scoring, next steps |

## Quick Start

```bash
bash install.sh
council --topic "Should this service use gRPC or REST?" --dry-run
council --topic "..." --backends claude,gemini
```

## Installation

| Platform | Method |
|----------|--------|
| Linux / WSL | `bash install.sh` |
| Termux (Android) | `bash install.sh` (no sudo) |
| pip | `pip install .` |

```bash
git clone https://github.com/M00C1FER/multi-agent-council
cd multi-agent-council
bash install.sh
```

## Usage

```python
from multi_agent_council import Council, SubprocessBackend

council = Council(backends=[
    SubprocessBackend("claude", cmd="claude"),
    SubprocessBackend("gemini", cmd="gemini"),
])

result = council.deliberate("Should we use Go or Rust for the network daemon?")

for phase, output in result.phase_outputs.items():
    print(f"\n── {phase} ──")
    print(output.summary)

print(f"\nDecision: {result.chairman_synthesis}")
print(f"Confidence: {result.confidence:.0%}")
if result.minority_report:
    print(f"Dissent: {result.minority_report}")
```

## Dry-Run Mode (no API required)

```bash
council --topic "..." --dry-run
```

Dry-run simulates all 7 phases with echo backends — useful for testing council structure without real AI invocations.

## Architecture (MOSA)

```
multi-agent-council/
├── src/multi_agent_council/
│   ├── council.py         # 7-phase state machine + ConsensusEngine bridge
│   └── __init__.py
├── install.sh             # Cross-platform wizard
├── examples/
│   ├── demo.py            # Dry-run two-agent council
│   └── custom_backend.py  # Implementing CLIBackend ABC
└── TOOLS.md
```

The `CLIBackend` ABC makes adding any AI CLI (or local model) a one-class extension — no core modifications needed.

## Adding a Custom Backend

```python
from multi_agent_council import CLIBackend, Message

class OllamaBackend(CLIBackend):
    name = "ollama"

    def send(self, message: Message) -> str:
        import subprocess
        result = subprocess.run(
            ["ollama", "run", "llama3", message.content],
            capture_output=True, text=True, timeout=120
        )
        return result.stdout.strip()
```

## Cross-Platform Notes

- **Linux/WSL:** Full feature set
- **Termux:** Works if AI CLIs are installed in Termux PATH
- **CI/offline:** Use `--dry-run` for pipeline testing

## License

[MIT](LICENSE)
