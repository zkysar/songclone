# Tasks: SongClone - Agentic Song Recreation System

**Input**: Design documents from `/specs/001-songclone/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Integration tests included per constitution (hackathon scope - critical paths only).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Backend**: `songclone/` Python package at repository root
- **Frontend**: `songclone/web/` React application
- **Tests**: `songclone/tests/integration/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [x] T001 Create directory structure per plan.md (`songclone/analysis/`, `songclone/reaper_mcp/`, `songclone/orchestrator/`, `songclone/api/`, `songclone/web/`)
- [x] T002 Initialize Python project with `pyproject.toml` including all dependencies (google-adk, google-genai, mcp, fastapi, uvicorn, pydantic, demucs, basic-pitch, madmom, librosa)
- [x] T003 [P] Create `songclone/__init__.py` and all subpackage `__init__.py` files
- [x] T004 [P] Initialize React project in `songclone/web/` with Vite, TypeScript, and TailwindCSS
- [x] T005 [P] Create `.env.example` with required environment variables (GOOGLE_API_KEY, REAPER_HOST, REAPER_PORT, MAX_ITERATIONS, QUALITY_THRESHOLD)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

### Pydantic Schemas (All Modules)

- [x] T006 [P] Create analysis schemas in `songclone/analysis/schemas.py` (Metadata, StemData, StemAnalysis, Structure, Section, ChordEvent, SongSpec)
- [x] T007 [P] Create orchestrator schemas in `songclone/orchestrator/schemas.py` (InstrumentConfig, MidiTransform, MixSettings, FXConfig, TrackPlan, ExecutionPlan, Scores, FeedbackItem, EvaluationResult)
- [x] T008 [P] Create API schemas in `songclone/api/schemas.py` (SessionCreated, Session, Iteration, Error)
- [x] T009 [P] Create SSE event schemas in `songclone/api/events.py` (PhaseEvent, IterationEvent, StepEvent, LogEvent, AudioEvent, HumanActionEvent, CompleteEvent, ErrorEvent)
- [x] T010 [P] Create TypeScript event types in `songclone/web/src/types/events.ts` matching Python SSE schemas

### Core Infrastructure

- [x] T011 Create session management in `songclone/api/session.py` (file-based state: create session directory, save/load session.json, generate UUID URLs)
- [x] T012 Create SSE broadcasting infrastructure in `songclone/api/events.py` (EventEmitter class with async queue, broadcast to connected clients)
- [x] T013 [P] Create retry utility with max 3 retries in `songclone/utils.py` (async retry decorator per constitution IV)
- [x] T014 Create FastAPI app skeleton in `songclone/api/main.py` (CORS setup, lifespan events, mount static files)

### REAPER MCP Server Foundation

- [x] T015 Create REAPER connection wrapper in `songclone/reaper_mcp/reaper_api.py` using reapy library (connection management, error handling)
- [x] T016 Create MCP server skeleton in `songclone/reaper_mcp/server.py` (stdio transport, tool registration per mcp-tools.json)

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Upload and Analyze Song (Priority: P1) 🎯 MVP

**Goal**: Users can upload audio and receive complete song analysis (tempo, key, sections, chords, stems with MIDI)

**Independent Test**: Upload a WAV file, verify SongSpec output contains all required fields

### Integration Test for User Story 1

- [x] T017 [US1] Create integration test in `songclone/tests/integration/test_analysis_pipeline.py` (test full pipeline with sample audio, assert SongSpec completeness)

### Analysis Pipeline Implementation

- [x] T018 [P] [US1] Implement Demucs stem separation in `songclone/analysis/demucs_runner.py` (separate to vocals, drums, bass, other WAVs)
- [x] T019 [P] [US1] Implement Basic Pitch MIDI extraction in `songclone/analysis/basic_pitch_runner.py` (extract MIDI from each stem, return base64-encoded)
- [x] T020 [P] [US1] Implement madmom beat/tempo detection in `songclone/analysis/madmom_runner.py` (detect BPM, time signature, downbeats)
- [x] T021 [P] [US1] Implement chord detection in `songclone/analysis/chord_runner.py` (librosa chroma features → chord matching → ChordEvent list)
- [x] T022 [P] [US1] Implement key detection in `songclone/analysis/chord_runner.py` (librosa.key → musical key string)
- [x] T023 [US1] Implement parallel analysis orchestration in `songclone/analysis/pipeline.py` (run T018-T022 concurrently with asyncio.gather, aggregate to SongSpec)
- [x] T024 [US1] Add section detection in `songclone/analysis/pipeline.py` (use beat positions to identify structure changes → Section list)

### API Endpoints for User Story 1

- [x] T025 [US1] Implement POST /api/sessions in `songclone/api/routes.py` (accept multipart audio upload, validate format/duration, create session, start analysis task)
- [x] T026 [US1] Implement GET /api/sessions/{id} in `songclone/api/routes.py` (return current session state from session.json)
- [x] T027 [US1] Implement GET /api/sessions/{id}/events SSE endpoint in `songclone/api/routes.py` (EventSourceResponse streaming from EventEmitter)
- [x] T028 [US1] Emit analysis progress events during pipeline execution (PhaseEvent for analysis start/complete, LogEvent for each tool)

### Frontend Upload Interface

- [x] T029 [P] [US1] Create useSSE hook in `songclone/web/src/hooks/useSSE.ts` (EventSource connection, reconnection logic, typed event parsing)
- [x] T030 [P] [US1] Create UploadArea component in `songclone/web/src/components/UploadArea.tsx` (drag-drop, file validation, upload progress)
- [x] T031 [US1] Create EventLog component in `songclone/web/src/components/EventLog.tsx` (display SSE log events in scrollable list)
- [x] T032 [US1] Wire App.tsx to show upload → analysis flow (conditional rendering based on session status)

**Checkpoint**: User Story 1 complete - users can upload songs and see full analysis results

---

## Phase 4: User Story 2 - View Recreation Iterations (Priority: P2)

**Goal**: After analysis, recreation begins automatically; users see plans, audio, scores, and feedback for each iteration

**Independent Test**: Trigger recreation, verify iterations appear with all components visible

### REAPER MCP Tools Implementation

- [x] T033 [P] [US2] Implement create_project tool in `songclone/reaper_mcp/tools.py` (create project with tempo/time signature per mcp-tools.json)
- [x] T034 [P] [US2] Implement batch_create_tracks tool in `songclone/reaper_mcp/tools.py` (create multiple tracks with VST instruments, handle fallback to ReaSynth)
- [x] T035 [P] [US2] Implement batch_insert_midi tool in `songclone/reaper_mcp/tools.py` (insert base64 MIDI data into tracks)
- [x] T036 [P] [US2] Implement batch_set_fx tool in `songclone/reaper_mcp/tools.py` (add FX chains to tracks)
- [x] T037 [P] [US2] Implement batch_set_levels tool in `songclone/reaper_mcp/tools.py` (set volume/pan/mute)
- [x] T038 [P] [US2] Implement render_audio tool in `songclone/reaper_mcp/tools.py` (render to WAV, return path)
- [x] T039 [P] [US2] Implement get_project_state tool in `songclone/reaper_mcp/tools.py` (return current track state for verification)

### Agent Prompts

- [x] T040 [P] [US2] Write planning agent system prompt in `songclone/orchestrator/prompts/planning.txt` (role definition, constraints, few-shot examples, output format)
- [x] T041 [P] [US2] Write evaluation agent system prompt in `songclone/orchestrator/prompts/evaluation.txt` (scoring rubric 1-10 per dimension, feedback format, stop criteria)

### Agent Implementations

- [x] T042 [US2] Implement Planning Agent in `songclone/orchestrator/agents/planning.py` (Google ADK agent with Gemini 3 Pro, thinking_level="high", output ExecutionPlan schema)
- [x] T043 [US2] Implement Execution Agent in `songclone/orchestrator/agents/execution.py` (MCP client calling REAPER tools per ExecutionPlan)
- [x] T044 [US2] Implement Evaluation Agent in `songclone/orchestrator/agents/evaluation.py` (Gemini 3 Pro with audio input, output EvaluationResult schema)
- [x] T045 [US2] Implement MFCC fallback evaluation in `songclone/orchestrator/agents/evaluation.py` (librosa MFCC comparison when AI fails)

### Orchestrator Loop

- [x] T046 [US2] Implement main agentic loop in `songclone/orchestrator/main.py` (plan → execute → evaluate → incorporate feedback → repeat)
- [x] T047 [US2] Emit iteration events during loop (IterationEvent start/complete, StepEvent for plan/execute/evaluate)
- [x] T048 [US2] Auto-start recreation after analysis completes in `songclone/api/routes.py` (launch orchestrator as background task)

### Frontend Iteration Display

- [x] T049 [P] [US2] Create IterationTimeline component in `songclone/web/src/components/IterationTimeline.tsx` (horizontal timeline with iteration cards, status indicators, score badges)
- [x] T050 [P] [US2] Create PlanViewer component in `songclone/web/src/components/PlanViewer.tsx` (collapsible JSON tree showing ExecutionPlan)
- [x] T051 [P] [US2] Create FeedbackDisplay component in `songclone/web/src/components/FeedbackDisplay.tsx` (score bars for 6 dimensions, prioritized feedback list)
- [x] T052 [US2] Add audio player for iteration renders (HTML5 audio element, autoplay disabled per constitution X)
- [x] T053 [US2] Wire App.tsx to display iteration view after analysis (show timeline, plan, scores, feedback)

### Integration Test for User Story 2

- [x] T054 [US2] Create integration test in `songclone/tests/integration/test_orchestrator_loop.py` (test single iteration cycle with mock REAPER)

**Checkpoint**: User Story 2 complete - users see full iteration loop with plans, audio, and feedback

---

## Phase 5: User Story 3 - Compare Original vs Recreation (Priority: P3)

**Goal**: Users can A/B compare original audio with any iteration's recreation

**Independent Test**: Load comparison view, verify both players work independently

### Audio Serving Endpoints

- [x] T055 [P] [US3] Implement GET /api/sessions/{id}/audio/original in `songclone/api/routes.py` (serve uploaded WAV)
- [x] T056 [P] [US3] Implement GET /api/sessions/{id}/audio/iteration/{n} in `songclone/api/routes.py` (serve rendered WAV for iteration n)

### Frontend Comparison Interface

- [x] T057 [US3] Create AudioComparison component in `songclone/web/src/components/AudioComparison.tsx` (dual audio players, iteration selector dropdown)
- [x] T058 [US3] Add comparison view toggle in App.tsx (show/hide comparison panel)

**Checkpoint**: User Story 3 complete - users can compare original vs any recreation

---

## Phase 6: User Story 4 - Automatic Quality Threshold Completion (Priority: P4)

**Goal**: System stops at 80% score or 10 iterations, user can download best result

**Independent Test**: Run until threshold/max, verify completion event and download works

### Stop Logic

- [x] T059 [US4] Implement threshold/max iteration stop logic in `songclone/orchestrator/main.py` (check EvaluationResult.stop_early or iteration >= max)
- [x] T060 [US4] Emit CompleteEvent with reason (threshold_reached, max_iterations) when loop ends

### Download Endpoint

- [x] T061 [US4] Implement GET /api/sessions/{id}/download in `songclone/api/routes.py` (return best iteration WAV with Content-Disposition header)

### Frontend Completion UI

- [x] T062 [US4] Display completion notification in App.tsx (success message with final scores)
- [x] T063 [US4] Add "Download Best" button in IterationTimeline (link to download endpoint)

**Checkpoint**: User Story 4 complete - users see automatic completion and can download best result

---

## Phase 7: Error Handling & Human-in-the-Loop

**Purpose**: Robust error handling and human intervention support per constitution

### Error Handling

- [x] T064 [P] Implement VST fallback logic in `songclone/reaper_mcp/tools.py` (try requested VST, fall back to ReaSynth, include fallback info in response)
- [x] T065 [P] Emit ErrorEvent on failures in all modules (per constitution IV - no silent failures)
- [x] T066 Add error display in App.tsx (show ErrorEvent messages, distinguish recoverable vs fatal)

### Human-in-the-Loop

- [x] T067 Implement 3-alternative retry before human request in `songclone/orchestrator/main.py` (per constitution V)
- [x] T068 Emit HumanActionEvent when intervention needed (description, reason, steps)
- [x] T069 Implement POST /api/sessions/{id}/resume in `songclone/api/routes.py` (verify state, resume orchestrator)
- [x] T070 Display human action request in App.tsx (show instructions, resume button)

### Cancel Support

- [x] T071 Implement POST /api/sessions/{id}/cancel in `songclone/api/routes.py` (stop orchestrator, preserve iterations)
- [x] T072 Add cancel button in App.tsx (per FR-022)

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Final improvements affecting multiple user stories

- [x] T073 [P] Create REAPER MCP integration test in `songclone/tests/integration/test_reaper_mcp.py` (test batch tools with running REAPER)
- [x] T074 Add session reconnection logic in App.tsx (check URL for session_id, reconnect to SSE)
- [x] T075 Code cleanup: ensure all functions have type hints (per constitution VII)
- [x] T076 Run quickstart.md validation end-to-end
- [x] T077 Verify all SSE event types match between Python and TypeScript

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-6)**: All depend on Foundational phase completion
  - US1 (Phase 3): Can start immediately after Foundation
  - US2 (Phase 4): Depends on US1 (needs SongSpec from analysis)
  - US3 (Phase 5): Depends on US2 (needs rendered iterations)
  - US4 (Phase 6): Depends on US2 (needs iteration loop)
- **Error Handling (Phase 7)**: Can run in parallel with US3/US4
- **Polish (Phase 8)**: Depends on all user stories being complete

### Parallel Opportunities

Within each phase, tasks marked [P] can run in parallel:

```bash
# Phase 2 parallel models:
T006, T007, T008, T009, T010 (all Pydantic schemas)

# Phase 3 parallel analysis runners:
T018, T019, T020, T021, T022 (all analysis tools)

# Phase 4 parallel MCP tools:
T033, T034, T035, T036, T037, T038, T039 (all REAPER tools)

# Phase 4 parallel prompts:
T040, T041 (planning and evaluation prompts)

# Phase 4 parallel frontend components:
T049, T050, T051 (iteration UI components)
```

---

## Implementation Strategy

### MVP First (User Story 1 + 2)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: User Story 1 (Upload/Analyze)
4. Complete Phase 4: User Story 2 (View Iterations)
5. **STOP and VALIDATE**: Test full analysis → iteration loop
6. Demo/present if ready

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. Add US1 → Can upload and analyze songs (demo value!)
3. Add US2 → Can see full recreation loop (core demo!)
4. Add US3 → Can compare audio (polish)
5. Add US4 → Auto-completion + download (complete)
6. Add Error Handling → Production-ready

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Verify tests fail before implementing
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- All SSE events must be typed in both Python (Pydantic) and TypeScript
- REAPER must be running for MCP integration tests
