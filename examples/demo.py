"""Demo: dry-run two-agent council with echo backends."""
from multi_agent_council import Council, DryRunBackend

council = Council(backends=[
    DryRunBackend("assistant-a"),
    DryRunBackend("assistant-b"),
])

result = council.deliberate(
    topic="Should this microservice use async/await or thread-based concurrency?",
    dry_run=True,
)

print(f"Topic     : {result.topic}")
print(f"Confidence: {result.confidence:.0%}")
if result.chairman_synthesis:
    print(f"Decision  : {result.chairman_synthesis}")
if result.minority_report:
    print(f"Dissent   : {result.minority_report}")
print()
for phase, output in result.phase_outputs.items():
    print(f"── {phase} ──")
    print(f"  {output[:120]}")
