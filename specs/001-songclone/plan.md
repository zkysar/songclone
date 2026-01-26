# Implementation Plan: SongClone - Agentic Song Recreation System

**Branch**: `001-songclone` | **Date**: 2026-01-26 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-songclone/spec.md`

## Summary

SongClone is an AI-powered system that recreates songs in REAPER DAW through an iterative agentic workflow. The system analyzes source audio (stem separation, MIDI extraction, tempo/key detection, chord recognition), generates recreation plans via Gemini 3 Pro, executes plans in REAPER via MCP, evaluates results using AI audio comparison (with MFCC fallback), and iterates until quality threshold (80%) or max iterations (10).

**Technical Approach**: Three-agent architecture (Planning, Execution, Evaluation) orchestrated via Google ADK, communicating through Pydantic schemas. Custom REAPER MCP server provides batch operations. React frontend streams SSE events for real-time visibility.

## Technical Context

**Language/Version**: Python 3.11+ (backend/orchestrator), TypeScript 5.x (frontend)
**Primary Dependencies**:
- Backend: google-adk, google-genai, mcp, fastapi, uvicorn, pydantic
- Analysis: demucs, basic-pitch, madmom, librosa
- Frontend: react, vite, tailwindcss
**Storage**: File-based only (WAV files, JSON state) - no database per constitution
**Testing**: pytest (integration tests for critical paths only per constitution)
**Target Platform**: Local deployment (macOS/Linux with REAPER installed)
**Project Type**: Web application (backend + frontend)
**Performance Goals**:
- Analysis: <3 min for 3-min song
- Full loop (10 iterations): <5 min for 3-min song
- UI latency: <500ms from server event to display
**Constraints**: REAPER must be running with ReaScript API enabled, single concurrent session
**Scale/Scope**: Single-user local deployment, hackathon demo scope

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Requirement | Status |
|-----------|-------------|--------|
| I. Stack | Uses Google ADK, Gemini 3 Pro, file-based state only | [x] |
| II. Agent Design | Single responsibility, Pydantic schemas, prompts in `/orchestrator/prompts/` | [x] |
| III. MCP & Tools | Batch ops preferred, typed responses, idempotent, REAPER verification | [x] |
| IV. Error Handling | SSE on errors, graceful VST fallback, parallel analysis, max 3 retries | [x] |
| V. Human-in-the-Loop | 3 alternatives before help, `human_action_required` events, pause/verify | [x] |
| VI. Hackathon | UI-demonstrable, no premature optimization, skip auth/persistence | [x] |
| VII. Code Standards | Type hints required, no "what" comments, minimal testing | [x] |
| VIII. Gemini 3 | Correct `thinking_level`, few-shot examples, WAV audio, <4000 token prompts | [x] |
| IX. Prompts | System=role+constraints, user=task+data, concrete criteria, scoring rubrics | [x] |
| X. UI Events | Typed events (TS/Python match), auto-play disabled | [x] |

## Project Structure

### Documentation (this feature)

```text
specs/001-songclone/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (API schemas)
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
songclone/
├── analysis/
│   ├── __init__.py
│   ├── pipeline.py           # Main analysis orchestration
│   ├── demucs_runner.py      # Stem separation
│   ├── basic_pitch_runner.py # MIDI extraction
│   ├── madmom_runner.py      # Beat/tempo detection
│   ├── chord_runner.py       # Chord detection (librosa-based)
│   └── schemas.py            # SongSpec, StemData Pydantic models

├── reaper_mcp/
│   ├── __init__.py
│   ├── server.py             # MCP server implementation
│   ├── tools.py              # Batch tool definitions
│   └── reaper_api.py         # ReaScript Python wrappers

├── orchestrator/
│   ├── __init__.py
│   ├── main.py               # Main agentic loop
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── planning.py       # Planning agent
│   │   ├── execution.py      # Execution agent
│   │   └── evaluation.py     # Evaluation agent
│   ├── prompts/
│   │   ├── planning.txt      # Planning system prompt
│   │   └── evaluation.txt    # Evaluation system prompt
│   └── schemas.py            # ExecutionPlan, EvaluationResult Pydantic models

├── api/
│   ├── __init__.py
│   ├── main.py               # FastAPI app
│   ├── routes.py             # API endpoints
│   ├── events.py             # SSE event handling
│   └── schemas.py            # API request/response Pydantic models

├── web/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── tailwind.config.js
│   ├── index.html
│   └── src/
│       ├── App.tsx
│       ├── main.tsx
│       ├── types/
│       │   └── events.ts     # SSE event TypeScript interfaces
│       ├── components/
│       │   ├── UploadArea.tsx
│       │   ├── IterationTimeline.tsx
│       │   ├── EventLog.tsx
│       │   ├── AudioComparison.tsx
│       │   ├── PlanViewer.tsx
│       │   └── FeedbackDisplay.tsx
│       └── hooks/
│           └── useSSE.ts

├── tests/
│   └── integration/
│       ├── test_analysis_pipeline.py
│       ├── test_reaper_mcp.py
│       └── test_orchestrator_loop.py

├── pyproject.toml
├── docker-compose.yml        # For analysis tools containerization
└── README.md
```

**Structure Decision**: Web application structure with `songclone/` as the main Python package containing backend modules (analysis, reaper_mcp, orchestrator, api) and `web/` for the React frontend. This matches the PRD file structure and supports the SSE-based real-time communication pattern.

## Complexity Tracking

> No constitution violations requiring justification. All principles are satisfied by design.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| N/A | - | - |
