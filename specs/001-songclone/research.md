# Research: SongClone

**Date**: 2026-01-26
**Branch**: `001-songclone`

## Technology Decisions

### 1. Audio Analysis Tools

#### Stem Separation: Demucs

**Decision**: Use `demucs` (Meta's hybrid transformer model) for stem separation.

**Rationale**:
- Industry-standard quality for 4-stem separation (vocals, drums, bass, other)
- Python API available via `demucs` package
- GPU acceleration optional but not required
- Outputs WAV files directly (matches constitution VIII requirement)

**Alternatives Considered**:
- Spleeter: Faster but lower quality separation
- Open-Unmix: Good quality but less maintained
- LALAL.AI API: External dependency, cost, latency

**Integration Pattern**:
```python
from demucs.apply import apply_model
from demucs.pretrained import get_model
# Use htdemucs model for best quality
```

#### MIDI Extraction: Basic Pitch

**Decision**: Use `basic-pitch` (Spotify's polyphonic pitch detection) for MIDI extraction.

**Rationale**:
- Handles polyphonic audio (multiple notes simultaneously)
- Direct MIDI output
- Works well on separated stems
- Active maintenance and good documentation

**Alternatives Considered**:
- CREPE: Monophonic only
- Melodia: Less accurate on polyphonic material
- AudioToMIDI: Commercial, closed source

**Integration Pattern**:
```python
from basic_pitch.inference import predict
from basic_pitch import ICASSP_2022_MODEL_PATH
# Run on each separated stem
```

#### Beat/Tempo Detection: madmom

**Decision**: Use `madmom` for tempo, beat tracking, and downbeat detection.

**Rationale**:
- State-of-the-art accuracy for beat tracking
- Provides downbeat positions (bar boundaries)
- Handles tempo changes
- Well-documented Python API

**Alternatives Considered**:
- librosa.beat: Less accurate, no downbeat detection
- Essentia: More complex API, overkill for this use case
- aubio: Good but madmom is more accurate

**Integration Pattern**:
```python
from madmom.features.beats import RNNBeatProcessor, DBNBeatTrackingProcessor
from madmom.features.downbeats import RNNDownBeatProcessor, DBNDownBeatTrackingProcessor
```

#### Chord Detection: librosa + custom

**Decision**: Use `librosa` for chroma features with rule-based chord matching.

**Rationale**:
- librosa provides robust chroma feature extraction
- Simple rule-based matching sufficient for major/minor chord detection
- No external API dependency
- Can be enhanced later if needed

**Alternatives Considered**:
- autochord: Abandoned project, installation issues
- Chordino (VAMP): Requires VAMP host, complex setup
- Commercial APIs: Cost, latency, dependency

**Integration Pattern**:
```python
import librosa
# Extract chroma features, match to chord templates
chroma = librosa.feature.chroma_cqt(y=audio, sr=sr)
```

#### Key Detection: librosa

**Decision**: Use `librosa.key` (Krumhansl-Schmuckler key-finding algorithm).

**Rationale**:
- Built into librosa, no additional dependency
- Sufficient accuracy for song recreation context
- Fast computation

**Integration Pattern**:
```python
from librosa import key
estimated_key = key(chroma)
```

### 2. Agent Orchestration: Google ADK

**Decision**: Use Google Agent Development Kit (ADK) for multi-agent orchestration.

**Rationale**:
- Constitution requirement (Principle I)
- Native Gemini integration
- Built-in tool calling support
- Typed schema support via Pydantic

**Best Practices**:
- Define each agent with a single responsibility
- Use `thinking_level="high"` for planning/evaluation
- Keep prompts under 4000 tokens
- Store prompts as separate files in `/orchestrator/prompts/`

**Agent Architecture**:
```
Planning Agent  → ExecutionPlan (Pydantic)
     ↓
Execution Agent → REAPER MCP tools → Rendered WAV
     ↓
Evaluation Agent → EvaluationResult (Pydantic)
     ↓
(loop back to Planning with feedback)
```

### 3. REAPER MCP Server

**Decision**: Custom MCP server with batch operations via ReaScript Python API.

**Rationale**:
- Constitution III requires batch operations
- Existing REAPER MCP implementations use individual calls (too slow)
- ReaScript provides full DAW control
- Local stdio transport for simplicity

**Batch Tools Defined**:
1. `create_project` - Initialize with tempo/time signature
2. `batch_create_tracks` - Multiple tracks with instruments
3. `batch_insert_midi` - MIDI data to multiple tracks
4. `batch_set_fx` - FX chains on multiple tracks
5. `batch_set_levels` - Volume/pan/mute for multiple tracks
6. `render_audio` - Render to WAV file
7. `get_project_state` - Verify state after operations

**REAPER Connection**:
- Use `reapy` library for ReaScript remote connection
- REAPER must have "Enable Python for use with ReaScript" enabled
- Connect via localhost TCP

### 4. Evaluation Strategy

**Decision**: Gemini 3 Pro audio comparison primary, MFCC fallback.

**Rationale**:
- Gemini 3 Pro supports audio input (WAV)
- Can provide semantic feedback ("bass too quiet")
- MFCC fallback ensures reliability per clarification

**Primary (AI) Evaluation**:
```python
# Send both WAVs to Gemini with scoring rubric
# thinking_level="high" for thorough analysis
# Returns scores + textual feedback
```

**Fallback (MFCC) Evaluation**:
```python
import librosa
# Extract MFCCs from both files
# Compute cosine similarity
# Map similarity to 0-10 scores
```

**Fallback Trigger**: If Gemini returns malformed response, timeout, or explicitly uncertain scores.

### 5. SSE Event Architecture

**Decision**: Server-Sent Events via FastAPI for real-time updates.

**Rationale**:
- Simpler than WebSockets for one-way streaming
- Native browser support (EventSource)
- FastAPI has built-in SSE support

**Event Types** (TypeScript/Pydantic matched):
```typescript
type SSEEvent =
  | { type: "phase"; phase: "analysis" | "iteration"; status: "started" | "complete"; data?: any }
  | { type: "iteration"; number: number; status: "started" | "complete" }
  | { type: "step"; step: "planning" | "execution" | "evaluation"; status: "started" | "complete"; data?: any }
  | { type: "log"; level: "info" | "warn" | "error"; message: string }
  | { type: "audio"; iteration: number; path: string }
  | { type: "human_action_required"; description: string; reason: string; steps: string[] }
  | { type: "complete"; reason: string; iterations: number }
  | { type: "error"; message: string; recoverable: boolean };
```

### 6. Session Management

**Decision**: File-based session state with unique URL per session.

**Rationale**:
- No database per constitution
- Session ID in URL enables reconnection
- JSON files store state (SongSpec, iterations, current status)

**Session File Structure**:
```
sessions/{session_id}/
├── session.json        # Status, config, iteration count
├── original.wav        # Uploaded file
├── song_spec.json      # Analysis output
├── iterations/
│   ├── 001/
│   │   ├── plan.json
│   │   ├── render.wav
│   │   └── evaluation.json
│   └── 002/
│       └── ...
```

### 7. Frontend Architecture

**Decision**: React + Vite + TailwindCSS single-page application.

**Rationale**:
- Fast development with Vite
- TailwindCSS for rapid styling
- React hooks for SSE subscription
- Matches hackathon velocity requirements

**Key Components**:
- `useSSE` hook: Manages EventSource connection, reconnection
- `UploadArea`: Drag-drop with progress
- `IterationTimeline`: Horizontal timeline with score badges
- `AudioComparison`: Dual HTML5 audio elements
- `PlanViewer`: Collapsible JSON tree (use `react-json-view`)
- `FeedbackDisplay`: Score bars + text feedback

### 8. Error Handling Strategy

**Decision**: SSE error events + graceful degradation + max 3 retries.

**Rationale**:
- Constitution IV requires no silent failures
- Graceful VST fallback to ReaSynth
- Parallel analysis with independent failure handling

**Implementation**:
```python
async def with_retry(operation, max_retries=3):
    for attempt in range(max_retries):
        try:
            return await operation()
        except ReaperError as e:
            if attempt == max_retries - 1:
                emit_sse_error(str(e), recoverable=False)
                raise
            emit_sse_log("warn", f"Retry {attempt+1}: {e}")
```

## Unresolved Items

None. All technical decisions are resolved.

## References

- [Demucs](https://github.com/facebookresearch/demucs) - Stem separation
- [Basic Pitch](https://github.com/spotify/basic-pitch) - MIDI extraction
- [madmom](https://github.com/CPJKU/madmom) - Beat tracking
- [librosa](https://librosa.org/) - Audio analysis
- [Google ADK](https://github.com/google/adk-python) - Agent orchestration
- [reapy](https://github.com/RomeoDespres/reapy) - REAPER Python API
- [MCP SDK](https://github.com/anthropics/mcp) - Model Context Protocol
