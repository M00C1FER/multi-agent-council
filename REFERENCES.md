# Reference Projects

Five high-star open-source multi-agent / AI-orchestration projects studied
during the audit cycle (2026-05-02). One concrete pattern noted from each.

---

## 1. microsoft/autogen — AutoGen
**Stars:** ~35 k · **License:** MIT
**URL:** https://github.com/microsoft/autogen

**Pattern adopted:** *Role-based conversation routing.*
AutoGen assigns each agent a named role (e.g. `AssistantAgent`, `UserProxy`,
`CriticAgent`) and routes messages through a topology graph. Multi-Agent
Council mirrors this with `_POSITION_ROLES` — roles are assigned by *session
position*, not by CLI identity, ensuring all backends remain equal peers.

---

## 2. crewAIInc/crewAI — CrewAI
**Stars:** ~25 k · **License:** MIT
**URL:** https://github.com/crewAIInc/crewAI

**Pattern adopted:** *Sequential vs parallel task execution.*
CrewAI supports both sequential and parallel crews. Multi-Agent Council's
`RECON` phase is intentionally sequential (no cross-pollination), while
`INTEL` broadcasts a shared blackboard — the same distinction CrewAI makes
between isolated research tasks and collaborative synthesis tasks.

---

## 3. langchain-ai/langgraph — LangGraph
**Stars:** ~7 k · **License:** MIT
**URL:** https://github.com/langchain-ai/langgraph

**Pattern adopted:** *State-machine with typed state schema.*
LangGraph encodes workflow state as a typed `TypedDict` that is passed between
nodes; each node declares which keys it reads and writes. This inspired the
per-phase Pydantic schemas (`BriefSchema`, `ReconSchema`, …) in
`HeadlessCouncil` — every phase transition is validated against a schema
before state is committed, preventing silent schema corruption bugs.

---

## 4. microsoft/semantic-kernel — Semantic Kernel
**Stars:** ~22 k · **License:** MIT
**URL:** https://github.com/microsoft/semantic-kernel

**Pattern adopted:** *Plugin / backend abstraction.*
Semantic Kernel defines a `KernelPlugin` ABC that any model provider
implements; callers never depend on the concrete provider. Multi-Agent
Council's `CLIBackend` ABC serves the same role: `SubprocessBackend`,
`DryRunBackend`, and user-defined backends (see `examples/custom_backend.py`)
all satisfy the same two-method contract (`name`, `query`), keeping core
orchestration code decoupled from specific AI CLIs.

---

## 5. BerriAI/litellm — LiteLLM
**Stars:** ~15 k · **License:** MIT
**URL:** https://github.com/BerriAI/litellm

**Pattern adopted:** *Timeout + retry with structured fallback.*
LiteLLM wraps every model call with a configurable timeout, a retry budget,
and a fallback response on exhaustion. Multi-Agent Council's
`execute_with_schema` (used in `HeadlessCouncil`) follows the same pattern:
`max_retries` attempts with schema-validation feedback on each failure, and
`HeadlessCouncil._run_agent_phase` catches any final exception and returns
`None`, letting the council continue with partial results rather than crashing.
