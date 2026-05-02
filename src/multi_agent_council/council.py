import sys
import argparse
import json
import logging
from typing import List, Literal, Dict
from pydantic import BaseModel, Field


logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("nexus.headless_council")

# ═══════════════════════════════════════════════════════════════
# PYDANTIC STRUCTURED OUTPUT SCHEMAS
# ═══════════════════════════════════════════════════════════════

from abc import ABC, abstractmethod


class CLIBackend(ABC):
    """Abstract base for CLI backends participating in council deliberation."""

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
            raw_response = agent.execute(enforced_prompt, timeout=timeout)

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
            agent = get_backend(name)
            self.agents.append(agent)
            self.agent_roles[agent.name] = role_info

        self.state: Dict[str, Dict[str, BaseModel]] = {
            "BRIEF": {}, "RECON": {}, "INTEL": {}, "WARGAME": {},
            "REFINE": {}, "COUNCIL": {}, "DEBRIEF": {}
        }

    def _print_phase(self, phase_name: str) -> None:
        print(f"\n\033[1;36m═════ COUNCIL — PHASE: {phase_name} ═════\033[0m")

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
            res = execute_with_schema(agent, prompt, BriefSchema)
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
            res = execute_with_schema(agent, prompt, ReconSchema, timeout=7200)
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
            res = execute_with_schema(agent, prompt, IntelSchema)
            self.state["INTEL"][agent.name] = res

        # PHASE 4: WARGAME (Adversarial)
        self._print_phase("WARGAME (Adversarial Challenge & Verification)")
        for i, agent in enumerate(self.agents):
            target = self.agents[(i + 1) % len(self.agents)].name
            target_pos = self.state["BRIEF"].get(target, BriefSchema(understanding="", critical_questions=[], initial_position="", assumptions=[])).initial_position
            target_recon = self.state["RECON"].get(target)

            prompt = (
                f"Role: RED TEAM\nMISSION: {self.topic}\n\n"
                f"TARGET POSITION (@{target}):\n{target_pos}\n"
                f"TARGET RECON:\n{target_recon.model_dump_json() if target_recon else 'None'}\n\n"
                f"Task: Identify weakest assumption, construct the strongest counterargument, and propose a failure scenario.\n"
                f"CRITICAL: Use your web search and MCP research tools to ACTIVELY VERIFY and fact-check the target's claims. If their data is flawed, prove it with external sources. Take up to 45 minutes if needed."
            )
            print(f"  → [@{agent.name}] Challenging @{target}... (Timeout: 1 hour)")
            res = execute_with_schema(agent, prompt, WargameSchema, timeout=3600)
            self.state["WARGAME"][agent.name] = res # agent's challenge against target

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
            res = execute_with_schema(agent, prompt, RefineSchema, timeout=3600)
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
            res = execute_with_schema(agent, prompt, CouncilSchema)
            self.state["COUNCIL"][agent.name] = res

        # PHASE 7: DEBRIEF
        self._print_phase("DEBRIEF (After Action Review)")
        council_consensus = ""
        for name, council in self.state["COUNCIL"].items():
            council_consensus += f"--- @{name} CONCLUSIONS ---\n{json.dumps(council.model_dump(), indent=2)}\n\n"

        for agent in self.agents:
            prompt = (
                f"MISSION: {self.topic}\n\n"
                f"COUNCIL CONSENSUS:\n{council_consensus}\n"
                f"Task: Identify success points, missed points, and rate the process."
            )
            print(f"  → [@{agent.name}] Debriefing...")
            res = execute_with_schema(agent, prompt, DebriefSchema)
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
    parser = argparse.ArgumentParser(description="Headless JSON-structured Think Tank")
    parser.add_argument("agents", help="Comma-separated agent names (e.g. claude,gemini,copilot)")
    parser.add_argument("topic", help="The topic to deliberate on")
    parser.add_argument("--mode", default="collaborate", help="Mode (ignored in headless think_tank dictating specific phases)")
    parser.add_argument("--depth", default="standard", help="Depth preset")
    parser.add_argument("--turns", type=int, default=0, help="Max turns")
    parser.add_argument("--budget", type=int, default=0, help="Time budget in seconds")
    parser.add_argument("--cli-list", help="Fallback original string from bash script", default="")

    args = parser.parse_args()

    agent_list = [a.strip() for a in args.agents.split(",") if a.strip()]
    if args.cli_list:
        agent_list = [a.strip() for a in args.cli_list.split(",") if a.strip()]

    if len(agent_list) < 2:
        print("Headless Council requires at least 2 agents.")
        sys.exit(1)

    council = HeadlessCouncil(args.topic, agent_list)
    try:
        council.run()
    except KeyboardInterrupt:
        print("\n[!] Council deliberation aborted.")
        sys.exit(130)

if __name__ == "__main__":
    main()
