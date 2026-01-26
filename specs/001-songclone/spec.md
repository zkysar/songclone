# Feature Specification: SongClone - Agentic Song Recreation System

**Feature Branch**: `001-songclone`
**Created**: 2026-01-26
**Status**: Draft
**Input**: User description: "AI-powered system that recreates songs in REAPER DAW through iterative agentic workflow"

## Clarifications

### Session 2026-01-26

- Q: Should recreation start automatically after analysis, or require user trigger? → A: Auto-start immediately after analysis completes
- Q: What happens if AI audio evaluation fails or is unreliable? → A: AI evaluation primary, with automatic fallback to spectral similarity metrics (MFCC comparison) if AI fails
- Q: Can users cancel a recreation in progress? → A: Yes, stop iteration loop and preserve completed iterations with their audio
- Q: Can users recover their session after browser refresh? → A: Yes, reconnect via URL or session ID to see current progress and history
- Q: What audio format for rendered iterations and downloads? → A: WAV only for highest quality and consistency with analysis pipeline

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Upload and Analyze Song (Priority: P1)

A user uploads an audio file to the web interface. The system analyzes the song to extract musical structure including tempo, key, chord progressions, and separated instrument stems (vocals, drums, bass, other). The user sees real-time progress updates during analysis.

**Why this priority**: Analysis is the foundation for all subsequent operations. Without accurate musical data extraction, the system cannot generate meaningful recreation plans. This is the entry point for all user interactions.

**Independent Test**: Can be fully tested by uploading a sample audio file and verifying the system produces a complete song specification with all required musical data. Delivers value by showing users the AI understands their song's structure.

**Acceptance Scenarios**:

1. **Given** a user on the upload page, **When** they drag and drop an MP3 or WAV file (up to 10 minutes duration), **Then** the system accepts the file and begins analysis with a progress indicator.

2. **Given** an audio file is being analyzed, **When** analysis completes, **Then** the system displays extracted metadata (tempo, key, time signature) and song structure (sections, chord progressions).

3. **Given** analysis is in progress, **When** the user views the interface, **Then** they see real-time status updates for each analysis step (stem separation, beat tracking, chord detection).

---

### User Story 2 - View Recreation Iterations (Priority: P2)

After analysis completes, recreation begins automatically without user intervention. The system recreates the song through multiple iterations. For each iteration, the user can see the AI's reasoning (plan), hear the rendered output, view evaluation scores, and see specific feedback on what will be improved next.

**Why this priority**: This demonstrates the core value proposition - showing AI reasoning and iterative improvement. Users need visibility into the decision-making process to understand and trust the system.

**Independent Test**: Can be tested by triggering recreation after analysis and verifying the UI displays plans, audio players, scores, and feedback for each iteration. Delivers value by making the AI's creative process transparent.

**Acceptance Scenarios**:

1. **Given** song analysis is complete, **When** recreation begins, **Then** the system shows a timeline of iterations with status indicators.

2. **Given** an iteration completes, **When** the user views that iteration, **Then** they see the AI's plan (instrument choices, mix settings), an audio player for the render, evaluation scores (timing, harmony, melody, instruments, mix, overall), and prioritized improvement feedback.

3. **Given** multiple iterations have completed, **When** the user views the timeline, **Then** they can see score progression across iterations and play any previous iteration's audio.

---

### User Story 3 - Compare Original vs Recreation (Priority: P3)

The user can compare the original uploaded song with any iteration's recreation using side-by-side audio players. This enables A/B listening to evaluate similarity and track improvement.

**Why this priority**: Comparison is essential for users to judge quality, but the system can function without it. Core functionality (analysis and iteration) must work first.

**Independent Test**: Can be tested by loading both original and rendered audio into comparison players and verifying synchronized playback controls work. Delivers value by enabling users to validate recreation quality.

**Acceptance Scenarios**:

1. **Given** at least one iteration has rendered, **When** the user opens the comparison view, **Then** they see two audio players (original and recreation) with synchronized timeline markers.

2. **Given** the comparison view is open, **When** the user selects a different iteration from a dropdown, **Then** the recreation player updates to that iteration's audio.

3. **Given** both players are loaded, **When** the user clicks play on either, **Then** playback is independent (not forced sync) allowing A/B switching.

---

### User Story 4 - Automatic Quality Threshold Completion (Priority: P4)

The system automatically stops iterating when the recreation reaches a quality threshold (80% score) or after a maximum number of iterations. The user is notified of completion with the final result.

**Why this priority**: Automatic stopping provides a natural endpoint to the process. However, users can still derive value from watching iterations even without automatic stopping.

**Independent Test**: Can be tested by running recreation until threshold is met or max iterations reached and verifying proper completion notification. Delivers value by providing clear success criteria.

**Acceptance Scenarios**:

1. **Given** an iteration scores 48/60 (80%) or higher, **When** evaluation completes, **Then** the system stops iterating and displays a success message with final scores.

2. **Given** 10 iterations have completed without reaching threshold, **When** the 10th iteration finishes, **Then** the system stops and displays a completion message with best achieved scores.

3. **Given** the system has stopped (by threshold or max), **When** the user views the final state, **Then** they see the complete iteration history and can download the best recreation as a WAV file.

---

### Edge Cases

- What happens when an uploaded file is not a valid audio format? System displays error message and prompts for valid audio file.
- What happens when audio analysis tools fail for a specific stem? System continues with remaining tools and marks failed analysis with fallback values.
- What happens when REAPER is not running or unreachable? System emits error event and pauses with clear instructions for user to start REAPER.
- What happens when a requested VST plugin is not available? System falls back to built-in instruments and logs the substitution.
- What happens when evaluation scores decrease between iterations? System continues (regression is valid feedback) and the evaluation agent adjusts strategy.
- What happens when AI audio evaluation fails or returns unreliable results? System automatically falls back to spectral similarity metrics (MFCC comparison) and continues iteration.
- What happens when the user closes the browser during processing? Processing continues server-side; user can reconnect via session URL to see current state and history.

## Requirements *(mandatory)*

### Functional Requirements

**Analysis Pipeline**
- **FR-001**: System MUST accept audio files in WAV or MP3 format up to 10 minutes duration.
- **FR-002**: System MUST separate uploaded audio into four stems: vocals, drums, bass, and other instruments.
- **FR-003**: System MUST extract MIDI note data from each separated stem.
- **FR-004**: System MUST detect tempo (BPM), time signature, and musical key from the audio.
- **FR-005**: System MUST identify chord progressions with timestamps.
- **FR-006**: System MUST identify song sections (intro, verse, chorus, etc.) with start/end times.
- **FR-007**: System MUST run analysis operations in parallel where dependencies allow.

**Recreation Loop**
- **FR-008**: System MUST generate an execution plan specifying tracks, instruments, MIDI assignments, and mix settings.
- **FR-009**: System MUST execute the plan by creating tracks, inserting MIDI, and applying effects in the DAW.
- **FR-010**: System MUST render each iteration to a WAV audio file for evaluation and playback.
- **FR-011**: System MUST evaluate rendered audio against the original on six dimensions (timing, harmony, melody, instruments, mix, overall) using AI audio comparison as the primary method.
- **FR-011a**: System MUST automatically fall back to spectral similarity metrics (MFCC comparison) if AI evaluation fails or returns unreliable results.
- **FR-012**: System MUST provide prioritized, actionable feedback for improvement after each evaluation.
- **FR-013**: System MUST incorporate previous evaluation feedback when generating the next iteration's plan.
- **FR-014**: System MUST stop when evaluation score reaches threshold (80%) or after maximum iterations (10).

**User Interface**
- **FR-015**: System MUST provide drag-and-drop file upload for audio files.
- **FR-016**: System MUST stream real-time progress events during analysis and iteration.
- **FR-017**: System MUST display the AI's execution plan in a readable format.
- **FR-018**: System MUST display evaluation scores with visual indicators (score bars).
- **FR-019**: System MUST provide audio playback for original and all rendered iterations.
- **FR-020**: System MUST display a timeline showing iteration progress and scores.
- **FR-021**: System MUST display prioritized improvement feedback from evaluations.
- **FR-022**: System MUST provide a cancel button to stop the iteration loop at any time.
- **FR-022a**: When cancelled, system MUST preserve all completed iterations and their rendered audio for playback and comparison.
- **FR-022b**: System MUST provide a unique session URL that allows users to reconnect and view progress after browser refresh or closure.

**Error Handling**
- **FR-023**: System MUST emit an error event (never silently fail) when any operation fails.
- **FR-024**: System MUST retry failed DAW operations up to 3 times before surfacing error to user.
- **FR-025**: System MUST fall back to built-in instruments when requested plugins are unavailable.
- **FR-026**: System MUST allow parallel analysis tools to fail independently without blocking others.

**Human-in-the-Loop**
- **FR-027**: System MUST attempt 3 alternative approaches before requesting human intervention.
- **FR-028**: System MUST pause and emit a specific event when human action is required (e.g., manual VST preset selection).
- **FR-029**: System MUST verify state after human confirms action completion before resuming.
- **FR-030**: System MUST log all human interventions for post-mortem analysis.

### Key Entities

- **SongSpec**: Complete analysis output for a song - includes metadata (tempo, key, time signature, duration), stems (separated audio paths + MIDI data for each), structure (sections with timestamps), and chord progressions.

- **ExecutionPlan**: AI-generated recreation strategy - includes track definitions (name, role, instrument, MIDI source), mix settings (volume, pan per track), effects configuration, and reasoning explanation.

- **EvaluationResult**: Quality assessment of a recreation - includes scores across six dimensions, total/max score, prioritized feedback items with categories and suggestions, and optional early-stop flag.

- **Iteration**: Single recreation attempt - links to its execution plan, rendered audio file, evaluation result, and iteration number.

- **RecreationSession**: Top-level container - includes original audio, SongSpec, list of iterations, current status, and final result.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can upload a song and view complete analysis results (tempo, key, sections, chords) within 3 minutes for a 3-minute song.

- **SC-002**: System completes 5 or more iterations without crashes or unrecoverable errors in 95% of sessions.

- **SC-003**: Evaluation scores show measurable improvement (increase in total score) in at least 60% of iteration pairs.

- **SC-004**: Full recreation loop (analysis through 10 iterations) completes within 5 minutes for a 3-minute song.

- **SC-005**: UI updates appear within 500ms of server events during the recreation process.

- **SC-006**: Final recreations are rated as "recognizably similar to original" by users at least 70% of the time (based on post-session feedback).

- **SC-007**: Users can successfully compare original vs recreation audio using the comparison feature in 100% of completed sessions.

- **SC-008**: Every feature is visually demonstrable in the UI (no hidden-only functionality).

## Assumptions

- REAPER DAW is installed and running with ReaScript API enabled on the host machine.
- At least one synthesizer VST (Vital, Dexed, or ReaSynth) is available for instrument recreation.
- FFmpeg is installed for audio format conversion.
- Users have modern web browsers supporting HTML5 audio and Server-Sent Events.
- Network latency between frontend and backend is negligible (same machine or local network).
- Audio files are royalty-free or user-owned (copyright compliance is user's responsibility).
- No authentication or user accounts are required (single-user local deployment).
- No persistent storage is needed between sessions (file-based state only).
