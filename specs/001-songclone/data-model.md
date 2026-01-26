# Data Model: SongClone

**Date**: 2026-01-26
**Branch**: `001-songclone`

## Core Entities

### Session

Top-level container for a recreation workflow.

| Field | Type | Description |
|-------|------|-------------|
| id | string (UUID) | Unique session identifier, used in URL |
| status | enum | `uploading`, `analyzing`, `iterating`, `paused`, `completed`, `failed`, `cancelled` |
| original_audio_path | string | Path to uploaded WAV file |
| song_spec | SongSpec? | Analysis output (null until analysis complete) |
| iterations | Iteration[] | List of completed iterations |
| current_iteration | int | Current iteration number (1-indexed) |
| max_iterations | int | Maximum iterations (default: 10) |
| quality_threshold | float | Stop threshold (default: 0.8 = 48/60) |
| created_at | datetime | Session creation timestamp |
| updated_at | datetime | Last update timestamp |
| error | string? | Error message if status is `failed` |

**State Transitions**:
```
uploading → analyzing → iterating → completed
                ↓           ↓
              failed      paused (human action required)
                            ↓
                         iterating (resume)
                            ↓
                         cancelled
```

### SongSpec

Complete analysis output for the uploaded song.

| Field | Type | Description |
|-------|------|-------------|
| metadata | Metadata | Global song properties |
| stems | dict[string, StemData] | Separated stems keyed by role |
| structure | Structure | Song section information |
| chords | ChordEvent[] | Chord progression with timestamps |

### Metadata

Global song properties extracted from analysis.

| Field | Type | Description |
|-------|------|-------------|
| duration_seconds | float | Total duration in seconds |
| tempo_bpm | float | Detected tempo in BPM |
| time_signature | string | e.g., "4/4", "3/4" |
| key | string | Detected key, e.g., "C major", "A minor" |

### StemData

Data for a single separated stem.

| Field | Type | Description |
|-------|------|-------------|
| role | enum | `vocals`, `drums`, `bass`, `other` |
| audio_path | string | Path to separated WAV file |
| midi_data | string | Base64-encoded MIDI file |
| analysis | StemAnalysis? | Role-specific analysis data |

### StemAnalysis

Role-specific analysis for each stem (polymorphic by role).

**Vocals**:
| Field | Type | Description |
|-------|------|-------------|
| detected_range | {low: string, high: string} | Note range, e.g., {"low": "E3", "high": "G5"} |

**Drums**:
| Field | Type | Description |
|-------|------|-------------|
| pattern_summary | string | Human-readable pattern, e.g., "4-on-floor kick, snare on 2&4" |

**Bass**:
| Field | Type | Description |
|-------|------|-------------|
| root_notes | string[] | Detected root notes, e.g., ["C", "G", "Am", "F"] |

**Other**:
| Field | Type | Description |
|-------|------|-------------|
| instrument_guess | string | Guessed instruments, e.g., "electric piano, synth pad" |

### Structure

Song section information.

| Field | Type | Description |
|-------|------|-------------|
| sections | Section[] | List of detected sections |

### Section

A single song section.

| Field | Type | Description |
|-------|------|-------------|
| name | string | Section type: "intro", "verse", "chorus", "bridge", "outro", etc. |
| start | float | Start time in seconds |
| end | float | End time in seconds |
| bars | int | Number of bars in section |

### ChordEvent

A chord at a specific timestamp.

| Field | Type | Description |
|-------|------|-------------|
| time | float | Start time in seconds |
| duration | float | Duration in beats |
| chord | string | Chord symbol, e.g., "C", "Am7", "G/B" |

### Iteration

A single recreation attempt.

| Field | Type | Description |
|-------|------|-------------|
| number | int | Iteration number (1-indexed) |
| plan | ExecutionPlan | AI-generated plan |
| render_path | string? | Path to rendered WAV (null if execution failed) |
| evaluation | EvaluationResult? | Evaluation results (null if not yet evaluated) |
| started_at | datetime | Iteration start timestamp |
| completed_at | datetime? | Iteration completion timestamp |
| status | enum | `planning`, `executing`, `evaluating`, `completed`, `failed` |

### ExecutionPlan

AI-generated recreation strategy.

| Field | Type | Description |
|-------|------|-------------|
| reasoning | string | Brief explanation of approach |
| tracks | TrackPlan[] | Track configurations |
| master_fx | FXConfig[] | Master bus effects |

### TrackPlan

Configuration for a single DAW track.

| Field | Type | Description |
|-------|------|-------------|
| name | string | Track name |
| role | enum | `vocals`, `drums`, `bass`, `other`, `master` |
| instrument | InstrumentConfig | VST/preset configuration |
| midi_source | string | Stem name to use for MIDI, or "generate" |
| midi_transform | MidiTransform? | Optional MIDI modifications |
| mix | MixSettings | Volume, pan settings |
| fx | FXConfig[] | Track effects chain |

### InstrumentConfig

VST instrument configuration.

| Field | Type | Description |
|-------|------|-------------|
| vst | string | VST plugin name, e.g., "Vital", "ReaSynth" |
| preset | string? | Preset name (optional) |

### MidiTransform

Optional MIDI modifications.

| Field | Type | Description |
|-------|------|-------------|
| transpose | int | Semitones to transpose (positive = up) |
| velocity_scale | float | Velocity multiplier (1.0 = no change) |

### MixSettings

Track mix configuration.

| Field | Type | Description |
|-------|------|-------------|
| volume_db | float | Volume in dB (0 = unity) |
| pan | float | Pan position (-1 = left, 0 = center, 1 = right) |
| mute | bool | Mute state (default: false) |

### FXConfig

Effect plugin configuration.

| Field | Type | Description |
|-------|------|-------------|
| plugin | string | Plugin name, e.g., "ReaEQ", "ReaComp" |
| preset | string? | Preset name (optional) |
| params | dict[string, any]? | Parameter overrides |

### EvaluationResult

Quality assessment of a recreation.

| Field | Type | Description |
|-------|------|-------------|
| scores | Scores | Scores across six dimensions |
| total_score | int | Sum of all scores (0-60) |
| max_score | int | Maximum possible score (60) |
| feedback | FeedbackItem[] | Prioritized improvement suggestions |
| stop_early | bool | True if quality is sufficient to stop |
| stop_reason | string? | Reason for early stop if applicable |
| evaluation_method | enum | `ai` or `mfcc_fallback` |

### Scores

Evaluation scores across six dimensions.

| Field | Type | Description |
|-------|------|-------------|
| timing | int | Tempo/timing accuracy (1-10) |
| harmony | int | Harmonic accuracy (1-10) |
| melody | int | Melodic accuracy (1-10) |
| instruments | int | Instrument selection appropriateness (1-10) |
| mix | int | Mix balance quality (1-10) |
| overall | int | Overall resemblance (1-10) |

### FeedbackItem

A single improvement suggestion.

| Field | Type | Description |
|-------|------|-------------|
| priority | int | Priority rank (1 = highest) |
| category | enum | `timing`, `harmony`, `melody`, `instruments`, `mix`, `other` |
| issue | string | Description of the problem |
| suggestion | string | Actionable improvement suggestion |

## SSE Events

Events streamed to the frontend during processing.

### PhaseEvent

| Field | Type | Description |
|-------|------|-------------|
| type | "phase" | Event type discriminator |
| phase | enum | `analysis`, `iteration` |
| status | enum | `started`, `complete` |
| data | any? | Phase-specific data |

### IterationEvent

| Field | Type | Description |
|-------|------|-------------|
| type | "iteration" | Event type discriminator |
| number | int | Iteration number |
| status | enum | `started`, `complete` |

### StepEvent

| Field | Type | Description |
|-------|------|-------------|
| type | "step" | Event type discriminator |
| step | enum | `planning`, `execution`, `evaluation` |
| status | enum | `started`, `complete` |
| data | any? | Step output (plan, render path, evaluation) |

### LogEvent

| Field | Type | Description |
|-------|------|-------------|
| type | "log" | Event type discriminator |
| level | enum | `info`, `warn`, `error` |
| message | string | Log message |

### AudioEvent

| Field | Type | Description |
|-------|------|-------------|
| type | "audio" | Event type discriminator |
| iteration | int | Iteration number |
| path | string | Path to rendered WAV |

### HumanActionEvent

| Field | Type | Description |
|-------|------|-------------|
| type | "human_action_required" | Event type discriminator |
| description | string | What action is needed |
| reason | string | Why automation failed |
| steps | string[] | Step-by-step instructions |

### CompleteEvent

| Field | Type | Description |
|-------|------|-------------|
| type | "complete" | Event type discriminator |
| reason | enum | `threshold_reached`, `max_iterations`, `cancelled` |
| iterations | int | Total iterations completed |

### ErrorEvent

| Field | Type | Description |
|-------|------|-------------|
| type | "error" | Event type discriminator |
| message | string | Error description |
| recoverable | bool | Whether the session can continue |

## Validation Rules

1. **Session.id**: Must be valid UUID v4
2. **Session.max_iterations**: Must be 1-20
3. **Session.quality_threshold**: Must be 0.0-1.0
4. **Metadata.tempo_bpm**: Must be 20-300
5. **Metadata.time_signature**: Must match pattern `\d+/\d+`
6. **StemData.role**: Must be one of defined enum values
7. **MixSettings.volume_db**: Must be -60 to +12
8. **MixSettings.pan**: Must be -1.0 to 1.0
9. **Scores.***: Each score must be 1-10
10. **FeedbackItem.priority**: Must be positive integer
