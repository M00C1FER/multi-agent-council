import sys
import argparse
import json
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Literal
from pydantic import BaseModel, Field


logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("nexus.headless_council")

# ═══════════════════════════════════════════════════════════════
# PYDANTIC STRUCTURED OUTPUT SCHEMAS
# ═══════════════════════════════════════════════════════════════

from abc import ABC, abstractmethod


class CLIBackend(ABC):
    """Abstract base for CLI backends participating in council deliberation."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable identifier for this backend."""

    @abstractmethod
    def query(self, prompt: str, timeout: int = 120) -> str:
        """Send a prompt and return the response text."""


class SubprocessBackend(CLIBackend):
    """Generic subprocess-based CLI backend.

    Args:
        backend_name: Human-readable name for this backend.
        cmd_template: Command as a list; use {prompt_file} placeholder for
                      a temp file path containing the prompt text.
        timeout: Default per-query timeout in seconds.

    Example::

        claude = SubprocessBackend(
            backend_name="claude",
            cmd_template=["claude", "--print", "--file", "{prompt_file}"],
        )
    """

    def __init__(self, backend_name: str, cmd_template: list, timeout: int = 120):
        self._name = backend_name
        self._cmd_template = cmd_template
        self._timeout = timeout

    @property
    def name(self) -> str:
        return self._name

    def query(self, prompt: str, timeout: int = 0) -> str:
        import subprocess
        import tempfile
        t = timeout or self._timeout
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as pf:
            pf.write(prompt)
            prompt_file = pf.name
        try:
            cmd = [
                c.replace("{prompt_file}", prompt_file) for c in self._cmd_template
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=t, check=False
            )
            return result.stdout.strip() or result.stderr.strip()
        except subprocess.TimeoutExpired:
            return f"[TIMEOUT after {t}s]"
        except FileNotFoundError:
            return f"[BACKEND_UNAVAILABLE: {self._name}]"
        finally:
            try:
                import os; os.unlink(prompt_file)
            except OSError:
                pass



class BriefSchema(BaseModel):
    understanding: str = Field(description="Understanding of the mission objective")
    critical_questions: List[str] = Field(description="Top 3 critical questions")
    initial_position: str = Field(description="Initial hypothesis")
    assumptions: List[str] = Field(description="Assumptions needing validation")

class ReconSchema(BaseModel):
    findings: List[str] = Field(description="Core researched findings")
    evidence: List[str] = Field(description="Supporting data/examples")
    risks: List[str] = Field(description="Identified risks/threats")

class IntelSchema(BaseModel):
    agreements: List[str] = Field(description="Points of consensus across peers")
    disagreements: List[str] = Field(description="Contradictions between peers")
    gaps: List[str] = Field(description="What everyone missed")
    synthesis: str = Field(description="Synthesized strongest elements")

class WargameSchema(BaseModel):
    weakest_assumption: str = Field(description="Weakest assumption in target position")
    counterargument: str = Field(description="Strongest counterargument")
    failure_scenario: str = Field(description="Scenario where position fails")

class RefineSchema(BaseModel):
    concessions: List[str] = Field(description="Valid points conceded")
    defense: List[str] = Field(description="Defense where evidence supports")
    refined_position: str = Field(description="Final refined position")
    confidence: Literal["HIGH", "MEDIUM", "LOW"] = Field(description="Confidence level")

class CouncilSchema(BaseModel):
    endorsements: List[str] = Field(description="Endorsed positions")
    rejections: List[str] = Field(description="Rejected positions")
    top_conclusions: List[str] = Field(description="Top 3 conclusions")
    minority_report: List[str] = Field(description="Positions held but rejected by others")
    confidence: Literal["HIGH", "MEDIUM", "LOW"] = Field(description="Overall confidence")

class DebriefSchema(BaseModel):
    success_points: List[str] = Field(description="What the council got right")
    missed_points: List[str] = Field(description="What the council missed")
    process_rating: Literal["EXCELLENT", "GOOD", "FAIR", "POOR"] = Field(description="Rating")

# ═══════════════════════════════════════════════════════════════
# PROMPT FORMATTERS
# ═══════════════════════════════════════════════════════════════

# Roles are assigned by SESSION POSITION, not by CLI identity.
# All CLIs (copilot, gemini, claude, ollama) are Full-Spectrum Nexus Commanders — equal peers.
# CLI EQUALITY STANDING ORDER: no CLI is pre-assigned a permanent limiting role.
_POSITION_ROLES = [
    {"role": "Lead Analyst",         "directive": "Structure the mission, decompose the problem, identify root causes and critical paths. Produce the first analysis artifact."},
    {"role": "Research Synthesizer", "directive": "Integrate evidence, ground claims in sources, build toward consensus. Challenge and extend the Analyst's initial framing."},
    {"role": "Adversarial Critic",   "directive": "Challenge assumptions, identify failure modes, stress-test conclusions from all participants. Represent the strongest objections."},
    {"role": "Implementation Lead",  "directive": "Translate analysis into concrete actions, code, configs, and next steps. Ensure the plan is executable."},
]
_FALLBACK_ROLE = {
    "role": "Full-Spectrum Analyst",
    "directive": "Apply full capabilities — reasoning, research, implementation, and validation — equally across all phases.",
}

def get_role_info(agent_name: str, position: int = 0) -> dict:
    """Return role info by session position, not by CLI identity.
    All CLIs are equal peers; roles rotate by invocation order."""
    if 0 <= position < len(_POSITION_ROLES):
        return _POSITION_ROLES[position]
    return _FALLBACK_ROLE

def extract_json(text: str) -> dict:
    """Attempt to extract a JSON block from free-text response."""
    text = text.strip()
    # Find first { and last }
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1 and end >= start:
        block = text[start:end+1]
        try:
            return json.loads(block)
        except json.JSONDecodeError:
            pass
    raise ValueError("Valid JSON not found in response")

def execute_with_schema(agent, prompt: str, schema_class: type[BaseModel], max_retries: int = 2, timeout: int = 7200) -> BaseModel:
    """Execute a prompt on a headless backend, forcing JSON output that matches the schema."""

    schema_json = schema_class.model_json_schema()
    enforced_prompt = (
        f"{prompt}\n\n"
        f"IMPORTANT INSTRUCTION:\n"
        f"You MUST output your response as EXACTLY valid JSON matching the following JSON Schema.\n"
        f"Do NOT include markdown blocks, '```json', or any conversational text outside the JSON object.\n\n"
        f"SCHEMA:\n{json.dumps(schema_json, indent=2)}\n"
    )

    for attempt in range(max_retries + 1):
        try:
            raw_response = agent.query(enforced_prompt, timeout=timeout)

            parsed_dict = extract_json(raw_response)
            validated = schema_class(**parsed_dict)
            return validated

        except Exception as e:
            if attempt < max_retries:
                logger.warning(f"@{agent.name} failed schema validation ({type(e).__name__}). Retrying... Error: {e}")
                logger.warning(f"Raw response was: {raw_response[:500]}...")
                enforced_prompt += f"\n\nERROR ON PREVIOUS ATTEMPT: {e}\nPlease correct the JSON output to strictly match the schema."
            else:
                logger.error(f"@{agent.name} failed schema validation after {max_retries} retries.")
                logger.error(f"Final raw response was: {raw_response[:500]}...")
                raise e

# ═══════════════════════════════════════════════════════════════
# ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════

def get_backend(backend: CLIBackend) -> CLIBackend:
    """Return the provided backend (identity — register backends via CouncilConfig)."""
    return backend


class HeadlessCouncil:
    def __init__(self, topic: str, agent_names: List[str]) -> None:
        self.topic = topic
        self.agent_roles = {}
        self.agents = []
        for position, name in enumerate(agent_names):
            role_info = get_role_info(name, position=position)
            # Create a SubprocessBackend from the CLI name; the default
            # cmd_template passes the prompt via a temp file as the first arg.
            # Users wanting non-default invocation should construct backends
            # explicitly and call HeadlessCouncil.from_backends() instead.
            agent = SubprocessBackend(
                backend_name=name,
                cmd_template=[name, "{prompt_file}"],
            )
            self.agents.append(agent)
            self.agent_roles[agent.name] = role_info

        self.state: Dict[str, Dict[str, BaseModel]] = {
            "BRIEF": {}, "RECON": {}, "INTEL": {}, "WARGAME": {},
            "REFINE": {}, "COUNCIL": {}, "DEBRIEF": {}
        }

    @classmethod
    def from_backends(cls, topic: str, backends: "List[CLIBackend]") -> "HeadlessCouncil":
        """Construct a :class:`HeadlessCouncil` from pre-built :class:`CLIBackend` instances.

        Use this when you need full control over the command template or timeout
        for each backend (e.g. ``claude --print --file {prompt_file}``).
        """
        instance = object.__new__(cls)
        instance.topic = topic
        instance.agent_roles = {}
        instance.agents = []
        for position, backend in enumerate(backends):
            role_info = get_role_info(backend.name, position=position)
            instance.agents.append(backend)
            instance.agent_roles[backend.name] = role_info
        instance.state = {
            "BRIEF": {}, "RECON": {}, "INTEL": {}, "WARGAME": {},
            "REFINE": {}, "COUNCIL": {}, "DEBRIEF": {}
        }
        return instance

    def _print_phase(self, phase_name: str) -> None:
        print(f"\n\033[1;36m═════ COUNCIL — PHASE: {phase_name} ═════\033[0m")

    def _run_agent_phase(self, agent: "CLIBackend", prompt: str, schema_class: type, timeout: int = 7200) -> "BaseModel | None":
        """Run a single agent through a phase, catching and logging any errors.

        Returns the validated schema instance, or ``None`` if the agent failed
        (timed out, unavailable, or returned unparse-able output).  Callers
        must guard against ``None`` before accessing schema attributes.
        """
        try:
            return execute_with_schema(agent, prompt, schema_class, timeout=timeout)
        except Exception as exc:
            logger.error(f"@{agent.name} failed phase ({type(exc).__name__}): {exc}")
            return None

    def run(self) -> None:
        # PHASE 1: BRIEF
        self._print_phase("BRIEF (Mission Framing)")
        for agent in self.agents:
            role = self.agent_roles[agent.name]
            prompt = (
                f"You are participating in a NEXUS Think-Tank deliberation.\n"
                f"Your assigned role: {role['role']} ({role['directive']})\n\n"
                f"MISSION: {self.topic}\n\n"
                f"Task: State your understanding, 3 critical questions, initial position, and assumptions."
            )
            print(f"  → [@{agent.name}] Briefing...")
            res = self._run_agent_phase(agent, prompt, BriefSchema)
            if res is not None:
                self.state["BRIEF"][agent.name] = res

        # PHASE 2: RECON
        self._print_phase("RECON (Deep Research & Analysis)")
        for agent in self.agents:
            role = self.agent_roles[agent.name]
            prompt = (
                f"Role: {role['role']}\nMISSION: {self.topic}\n\n"
                f"This is an EXHAUSTIVE DEEP RESEARCH PHASE. You have authorization to take as much time as necessary (up to 60-120 minutes) to perform deep research.\n"
                f"CRITICAL INSTRUCTION: You MUST use your available MCP tools (e.g., web_search_task, fetch_url, or native browsing) to gather empirical evidence.\n"
                f"Do NOT rely solely on your baseline knowledge. Mirror top-tier research systems by reviewing 50-100+ sources if necessary. Leave no stone unturned.\n"
                f"Conduct thorough analysis from YOUR perspective.\n"
                f"Provide core findings, exhaustive evidence/data, and identify risks."
            )
            print(f"  → [@{agent.name}] Conducting Deep Reconnaissance... (Timeout: 2 hours)")
            res = self._run_agent_phase(agent, prompt, ReconSchema, timeout=7200)
            if res is not None:
                self.state["RECON"][agent.name] = res

        # PHASE 3: INTEL (Blackboard Sync)
        self._print_phase("INTEL (Blackboard Synthesis)")
        blackboard = ""
        for name, recon in self.state["RECON"].items():
            blackboard += f"--- @{name} RECON ---\n{json.dumps(recon.model_dump(), indent=2)}\n\n"

        for agent in self.agents:
            role = self.agent_roles[agent.name]
            prompt = (
                f"Role: {role['role']}\nMISSION: {self.topic}\n\n"
                f"BLACKBOARD — All participants' RECON findings:\n{blackboard}\n"
                f"Task: Identify agreements, disagreements, gaps, and synthesize stronger elements."
            )
            print(f"  → [@{agent.name}] Synthesizing Intel...")
            res = self._run_agent_phase(agent, prompt, IntelSchema)
            if res is not None:
                self.state["INTEL"][agent.name] = res

        # PHASE 4: WARGAME (Adversarial)
        self._print_phase("WARGAME (Adversarial Challenge & Verification)")
        for i, agent in enumerate(self.agents):
            target = self.agents[(i + 1) % len(self.agents)].name
            brief_fallback = BriefSchema(
                understanding="",
                critical_questions=[],
                initial_position="",
                assumptions=[],
            )
            target_pos = self.state["BRIEF"].get(target, brief_fallback).initial_position
            target_recon = self.state["RECON"].get(target)

            prompt = (
                f"Role: RED TEAM\nMISSION: {self.topic}\n\n"
                f"TARGET POSITION (@{target}):\n{target_pos}\n"
                f"TARGET RECON:\n{target_recon.model_dump_json() if target_recon else 'None'}\n\n"
                f"Task: Identify weakest assumption, construct the strongest counterargument, and propose a failure scenario.\n"
                f"CRITICAL: Use your web search and MCP research tools to ACTIVELY VERIFY and fact-check the target's claims. If their data is flawed, prove it with external sources. Take up to 45 minutes if needed."
            )
            print(f"  → [@{agent.name}] Challenging @{target}... (Timeout: 1 hour)")
            res = self._run_agent_phase(agent, prompt, WargameSchema, timeout=3600)
            if res is not None:
                self.state["WARGAME"][agent.name] = res

        # PHASE 5: REFINE
        self._print_phase("REFINE (Position Update & Fact Checking)")
        for i, agent in enumerate(self.agents):
            challenger = self.agents[(i - 1) % len(self.agents)].name
            wargame_challenge = self.state["WARGAME"].get(challenger)

            prompt = (
                f"MISSION: {self.topic}\n\n"
                f"CHALLENGES RECEIVED from @{challenger}:\n{wargame_challenge.model_dump_json() if wargame_challenge else 'None'}\n\n"
                f"Task: Address challenges, concede points, defend position, and state refined position with confidence.\n"
                f"CRITICAL INSTRUCTION: Do NOT blindly concede or defend. Use your MCP and web search tools to ACTIVELY verify the counterarguments. Dig deep into the sources. You have up to 45 minutes to fact-check before finalizing your position."
            )
            print(f"  → [@{agent.name}] Refining Position... (Timeout: 1 hour)")
            res = self._run_agent_phase(agent, prompt, RefineSchema, timeout=3600)
            if res is not None:
                self.state["REFINE"][agent.name] = res

        # PHASE 6: COUNCIL
        self._print_phase("COUNCIL (Formal Vote & Synthesis)")
        all_refined = ""
        for name, refine in self.state["REFINE"].items():
            all_refined += f"--- @{name} REFINED POSITION ---\n{json.dumps(refine.model_dump(), indent=2)}\n\n"

        for agent in self.agents:
            prompt = (
                f"MISSION: {self.topic}\n\n"
                f"ALL REFINED POSITIONS:\n{all_refined}\n"
                f"Task: Endorse/reject positions, state top 3 conclusions, write minority report, and assess overall confidence."
            )
            print(f"  → [@{agent.name}] Voting in Council...")
            res = self._run_agent_phase(agent, prompt, CouncilSchema)
            if res is not None:
                self.state["COUNCIL"][agent.name] = res

        # PHASE 7: DEBRIEF
        self._print_phase("DEBRIEF (After Action Review)")
        council_consensus = ""
        for name, council_vote in self.state["COUNCIL"].items():
            council_consensus += f"--- @{name} CONCLUSIONS ---\n{json.dumps(council_vote.model_dump(), indent=2)}\n\n"

        for agent in self.agents:
            prompt = (
                f"MISSION: {self.topic}\n\n"
                f"COUNCIL CONSENSUS:\n{council_consensus}\n"
                f"Task: Identify success points, missed points, and rate the process."
            )
            print(f"  → [@{agent.name}] Debriefing...")
            res = self._run_agent_phase(agent, prompt, DebriefSchema)
            if res is not None:
                self.state["DEBRIEF"][agent.name] = res

        self._finalize()

    def _finalize(self) -> str:
        print("\n\033[1;32m═════ THINK TANK SYNTHESIS COMPLETE ═════\033[0m")
        # Compile a final markdown overview
        output = [f"# Think Tank Deliberation: {self.topic}\n"]
        output.append("## Participants: " + ", ".join([f"@{a.name}" for a in self.agents]) + "\n")

        output.append("## 1. Core Findings (Recon Synthesis)")
        for a in self.agents:
            if a.name in self.state["RECON"]:
                r = self.state["RECON"][a.name]
                output.append(f"### @{a.name}")
                for f in r.findings:
                    output.append(f"- {f}")

        output.append("\n## 2. Top Council Conclusions")
        for a in self.agents:
            if a.name in self.state["COUNCIL"]:
                c = self.state["COUNCIL"][a.name]
                output.append(f"### @{a.name} (Confidence: {c.confidence})")
                for tc in c.top_conclusions:
                    output.append(f"- {tc}")

        output.append("\n## 3. Disagreements / Minority Reports")
        for a in self.agents:
            if a.name in self.state["COUNCIL"]:
                c = self.state["COUNCIL"][a.name]
                if c.minority_report:
                    output.append(f"### @{a.name}")
                    for mr in c.minority_report:
                        output.append(f"- {mr}")

        final_md = "\n".join(output)
        print("\n" + final_md)
        return final_md

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Multi-Agent Council — 7-phase structured deliberation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  council --topic 'gRPC vs REST?' --dry-run\n"
            "  council --topic '...' --backends claude,gemini\n"
            "  council --phases\n"
        ),
    )
    parser.add_argument("--topic", required=False, default="", help="Topic to deliberate on")
    parser.add_argument(
        "--backends",
        default="",
        help="Comma-separated backend CLI names (e.g. claude,gemini,copilot)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate all 7 phases with echo backends — no real AI calls",
    )
    parser.add_argument(
        "--phases",
        action="store_true",
        help="List the 7 council phases and exit",
    )

    args = parser.parse_args()

    if args.phases:
        print("Council phases (in order):")
        for i, phase in enumerate(_COUNCIL_PHASES, 1):
            print(f"  {i}. {phase}")
        return

    if not args.topic:
        parser.error("--topic is required (or use --phases to list phases)")

    if args.dry_run:
        backends: "List[CLIBackend]" = [DryRunBackend("agent-a"), DryRunBackend("agent-b")]
        council_obj = Council(backends=backends)
        result = council_obj.deliberate(args.topic, dry_run=True)
        print(f"\nTopic     : {result.topic}")
        print(f"Confidence: {result.confidence:.0%}")
        if result.chairman_synthesis:
            print(f"Decision  : {result.chairman_synthesis}")
        if result.minority_report:
            print(f"Dissent   : {result.minority_report}")
        print()
        for phase, output in result.phase_outputs.items():
            print(f"── {phase} ──")
            print(f"  {output[:120]}")
        return

    agent_list = [a.strip() for a in args.backends.split(",") if a.strip()]
    if len(agent_list) < 2:
        parser.error("--backends requires at least 2 comma-separated backend names")

    council = HeadlessCouncil(args.topic, agent_list)
    try:
        council.run()
    except KeyboardInterrupt:
        print("\n[!] Council deliberation aborted.")
        sys.exit(130)

if __name__ == "__main__":
    main()


# ── Public API additions ──────────────────────────────────────────────────

_COUNCIL_PHASES = ("BRIEF", "RECON", "INTEL", "WARGAME", "REFINE", "COUNCIL", "DEBRIEF")


class DryRunBackend(CLIBackend):
    """A no-op backend for testing that echoes the topic without calling any external CLI.

    Args:
        backend_name: Human-readable name returned by :meth:`name`.

    Example::

        backends = [DryRunBackend("agent_a"), DryRunBackend("agent_b")]
        council = Council(backends)
        result = council.deliberate("Is Python better than Go?", dry_run=True)
    """

    def __init__(self, backend_name: str) -> None:
        self._name = backend_name

    @property
    def name(self) -> str:
        return self._name

    def query(self, prompt: str, timeout: int = 120) -> str:  # noqa: ARG002
        return f"[DryRun:{self._name}] Acknowledged: {prompt[:80]}"


@dataclass
class CouncilResult:
    """Result of a :class:`Council` deliberation.

    Attributes:
        topic: The deliberation topic.
        confidence: Aggregate confidence score (0.0–1.0).
        phase_outputs: Mapping of phase name → combined backend responses.
            Always contains exactly 7 keys: ``BRIEF``, ``RECON``, ``INTEL``,
            ``WARGAME``, ``REFINE``, ``COUNCIL``, ``DEBRIEF``.
        chairman_synthesis: High-level synthesis produced from the COUNCIL phase.
        minority_report: Dissenting positions (empty string if unanimous).
    """
    topic: str
    confidence: float
    phase_outputs: "Dict[str, str]"
    chairman_synthesis: str = ""
    minority_report: str = ""

    def __post_init__(self) -> None:
        for phase in _COUNCIL_PHASES:
            self.phase_outputs.setdefault(phase, "")


class Council:
    """High-level 7-phase think-tank council.

    This is a simplified, dependency-free interface for driving the 7-phase
    deliberation protocol without the full NEXUS daemon stack.  Each phase
    queries all *backends* in round-robin fashion; responses are aggregated
    into a single :class:`CouncilResult`.

    Args:
        backends: List of :class:`CLIBackend` implementations to include.
            At least one backend is required.

    Example::

        backends = [DryRunBackend("claude"), DryRunBackend("gemini")]
        result = Council(backends).deliberate("Evaluate microservices vs monolith")
        print(result.confidence)
    """

    PHASES = _COUNCIL_PHASES

    def __init__(self, backends: "List[CLIBackend]") -> None:
        if not backends:
            raise ValueError("Council requires at least one backend.")
        self.backends = backends

    def deliberate(self, topic: str, dry_run: bool = False) -> CouncilResult:  # noqa: ARG002
        """Run the 7-phase deliberation and return a :class:`CouncilResult`.

        Args:
            topic: The question or subject to deliberate on.
            dry_run: When *True*, backends are called exactly as normal — the
                flag is present for API compatibility with callers that want
                to signal intent; use :class:`DryRunBackend` to suppress
                actual subprocess calls.

        Returns:
            :class:`CouncilResult` with outputs for all 7 phases.
        """
        phase_outputs: "Dict[str, str]" = {}
        cumulative_context = f"Topic: {topic}\n"

        for phase in self.PHASES:
            phase_prompt = (
                f"{cumulative_context}\n--- Phase: {phase} ---\n"
                f"Provide your analysis for the {phase} phase of the deliberation."
            )
            responses = []
            for backend in self.backends:
                try:
                    resp = backend.query(phase_prompt, timeout=60)
                except Exception as exc:  # noqa: BLE001
                    resp = f"[ERROR:{backend.name}] {exc}"
                responses.append(f"[{backend.name}] {resp}")
            combined = "\n".join(responses)
            phase_outputs[phase] = combined
            cumulative_context += f"\n### {phase}\n{combined}\n"

        # Simple confidence: fraction of backends that produced non-error responses
        all_responses = "\n".join(phase_outputs.values())
        error_count = all_responses.count("[ERROR:")
        total_calls = len(self.PHASES) * len(self.backends)
        confidence = max(0.0, 1.0 - (error_count / max(total_calls, 1)))

        # Derive chairman_synthesis: first non-error, non-empty line from COUNCIL phase.
        council_output = phase_outputs.get("COUNCIL", "")
        non_error_lines = [
            line.strip()
            for line in council_output.splitlines()
            if line.strip()
            and not line.strip().startswith("[ERROR:")
            and not line.strip().startswith("[TIMEOUT")
        ]
        chairman_synthesis = non_error_lines[0] if non_error_lines else ""

        # minority_report requires structured per-agent tracking available in
        # HeadlessCouncil (pydantic schemas). Council.deliberate() produces a
        # flat combined string per phase, so dissent detection is not possible
        # here without re-parsing. Return empty string; callers needing full
        # minority tracking should use HeadlessCouncil directly.
        minority_report = ""

        return CouncilResult(
            topic=topic,
            confidence=round(confidence, 4),
            phase_outputs=phase_outputs,
            chairman_synthesis=chairman_synthesis,
            minority_report=minority_report,
        )
