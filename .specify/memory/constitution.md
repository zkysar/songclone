<!--
================================================================================
SYNC IMPACT REPORT
================================================================================
Version Change: N/A → 1.0.0 (initial adoption)
Modified Principles: N/A (new constitution)
Added Sections: Stack, Agent Design, MCP & Tools, Error Handling, Human-in-the-Loop,
                Hackathon Priorities, Code Standards, Gemini 3 Usage, Prompt Engineering,
                UI Events, Governance
Removed Sections: N/A
Templates Requiring Updates:
  - .specify/templates/plan-template.md: ✅ updated (Constitution Check section populated)
  - .specify/templates/spec-template.md: ✅ compatible (no constitution-specific references)
  - .specify/templates/tasks-template.md: ✅ compatible (no constitution-specific references)
Follow-up TODOs: None
================================================================================
-->

# SongClone Constitution

## Core Principles

### I. Stack

- Google ADK MUST be used for agent orchestration
- Gemini 3 Pro (`gemini-3-pro-preview`) MUST be used for all reasoning tasks
- No external databases permitted; file-based state only

**Rationale**: Standardizes the technology foundation and simplifies deployment by avoiding database dependencies.

### II. Agent Design

- Each agent MUST have exactly ONE responsibility (single responsibility principle)
- Agents MUST communicate via typed schemas (Pydantic); raw strings are prohibited
- Agent prompts MUST live in `/orchestrator/prompts/` as separate files, not inline

**Rationale**: Enforces modularity, type safety, and maintainability of the agent system.

### III. MCP & Tools

- Batch operations MUST be preferred over individual calls to minimize round-trips
- Every tool MUST return a typed response; returning only "success" is prohibited
- Tools MUST be idempotent where possible (re-running is safe)
- REAPER state MUST be verified after every batch operation

**Rationale**: Ensures reliability, debuggability, and efficiency of tool interactions.

### IV. Error Handling

- Silent failures are prohibited; an SSE event MUST be emitted on any error
- Graceful degradation is required: if a VST is missing, REAPER built-ins MUST be used
- Analysis tool failures MUST NOT block other tools (parallel execution with fallbacks)
- Maximum 3 retries per REAPER operation before surfacing error to user

**Rationale**: Maintains system resilience and keeps users informed of issues.

### V. Human-in-the-Loop

- When blocked, the system MUST first attempt 3 alternative approaches before requesting human help
- If automation is truly impossible (e.g., VST requires manual preset selection, REAPER dialog
  needs click), a `human_action_required` event MUST be emitted with:
  - Clear description of what is needed
  - Why automation failed
  - Exact steps for the user to perform
- The iteration loop MUST pause while awaiting human input (no spinning)
- After human confirms action complete, state MUST be verified before resuming
- All human interventions MUST be logged for post-mortem analysis

**Rationale**: Balances automation with pragmatic human intervention when necessary.

### VI. Hackathon Priorities

- Every feature MUST be visually demonstrable in the UI
- No premature optimization; make it work first
- Authentication, user management, and persistence are explicitly skipped
- Hard-coded configs are acceptable; no settings UI required

**Rationale**: Optimizes for rapid demonstration and iteration during hackathon timelines.

### VII. Code Standards

- Type hints are REQUIRED on all function signatures
- Comments explaining "what" are prohibited; code MUST be self-evident
- Comments are permitted only for "why" (non-obvious decisions)
- Testing is minimal; integration tests are required only for critical paths

**Rationale**: Maintains code quality while avoiding documentation overhead.

### VIII. Gemini 3 Usage

- `thinking_level="high"` MUST be set for planning and evaluation tasks
- `thinking_level="low"` MUST be used for simple formatting tasks
- Few-shot examples MUST be included in prompts for complex outputs
- Audio inputs MUST be sent as WAV, not MP3 (better quality for analysis)
- Prompts MUST be kept under 4000 tokens; context MUST be summarized, not dumped

**Rationale**: Optimizes model performance and cost for different task types.

### IX. Prompt Engineering

- System prompts MUST define role and constraints only
- User messages MUST contain the specific task plus data
- Prompts MUST NOT ask Gemini to "be creative"; concrete criteria are required
- Scoring rubrics MUST be included in evaluation prompts

**Rationale**: Ensures consistent, reproducible, and evaluable model outputs.

### X. UI Events

- Events MUST be typed (TypeScript interfaces matching Python schemas)
- Auto-play MUST be disabled by default; user initiates playback

**Rationale**: Ensures type safety between backend and frontend while respecting user control.

## Governance

This constitution supersedes all other project practices and guidelines. All implementation
decisions MUST comply with the principles defined above.

### Amendment Procedure

1. Proposed amendments MUST be documented with rationale
2. Amendments require explicit approval before adoption
3. Breaking changes to principles require a migration plan
4. Version increments follow semantic versioning:
   - MAJOR: Backward-incompatible principle removals or redefinitions
   - MINOR: New principles added or materially expanded guidance
   - PATCH: Clarifications, wording, typo fixes, non-semantic refinements

### Compliance Review

- All code reviews MUST verify compliance with this constitution
- Violations MUST be justified in the Complexity Tracking section of the implementation plan
- Complexity MUST be justified; YAGNI (You Aren't Gonna Need It) principles apply

**Version**: 1.0.0 | **Ratified**: 2026-01-26 | **Last Amended**: 2026-01-26
