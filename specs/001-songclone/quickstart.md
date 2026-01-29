# Quickstart: SongClone

**Branch**: `001-songclone`
**Date**: 2026-01-26

## Prerequisites

### System Requirements

- **OS**: macOS or Linux
- **Python**: 3.11+
- **Node.js**: 18+
- **REAPER**: v7+ with ReaScript enabled

### REAPER Setup

1. Open REAPER Preferences (`Cmd+,` on macOS)
2. Navigate to `Plug-ins` → `ReaScript`
3. Enable "Allow remote ReaScript execution"
4. Set TCP port to `9000`
5. Ensure Python is configured (use system Python 3.11+)

### External Dependencies

```bash
# FFmpeg for audio conversion
brew install ffmpeg  # macOS
# or
apt-get install ffmpeg  # Linux

# Optional: GPU support for faster Demucs
pip install torch torchaudio  # with CUDA support if available
```

## Installation

### 1. Clone and Setup

```bash
cd /path/to/songclone
git checkout 001-songclone

# Create Python virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -e ".[dev]"
```

### 2. Frontend Setup

```bash
cd songclone/web
npm install
```

### 3. Environment Configuration

Create `.env` in project root:

```bash
# Required
GOOGLE_API_KEY=your_gemini_api_key

# Optional (defaults shown)
REAPER_HOST=localhost
REAPER_PORT=9000
MAX_ITERATIONS=10
QUALITY_THRESHOLD=0.8
ANALYSIS_WORKERS=4
```

## Running

### Development Mode

Terminal 1 - Backend:
```bash
source venv/bin/activate
uvicorn songclone.api.main:app --reload --port 8000
```

Terminal 2 - Frontend:
```bash
cd songclone/web
npm run dev
```

Terminal 3 - Ensure REAPER is running with a blank project open.

### Access

Open http://localhost:5173 in your browser.

## Usage

### 1. Upload a Song

- Drag and drop a WAV or MP3 file (max 10 minutes)
- Or click to browse files

### 2. Watch Analysis

The system will:
- Separate stems (vocals, drums, bass, other)
- Extract MIDI from each stem
- Detect tempo, key, and time signature
- Identify chord progressions
- Map song structure (intro, verse, chorus, etc.)

### 3. Observe Recreation Loop

After analysis, recreation starts automatically:
1. **Planning**: AI generates a recreation plan
2. **Execution**: Plan is executed in REAPER
3. **Evaluation**: Result is compared to original
4. **Iteration**: Feedback improves next attempt

### 4. Compare Results

- Use the audio comparison panel for A/B listening
- View score progression in the timeline
- Read detailed feedback for each iteration

### 5. Download Result

- Click "Download Best" to get the highest-scoring recreation
- Output is always WAV format

## Troubleshooting

### REAPER Connection Failed

```
Error: Could not connect to REAPER
```

1. Ensure REAPER is running
2. Check ReaScript preferences are correct
3. Verify port 9000 is not blocked
4. Try restarting REAPER

### VST Not Found

```
Warning: Vital not found, using ReaSynth
```

This is expected behavior per constitution. The system falls back to REAPER's built-in instruments when requested VSTs are unavailable.

### Analysis Timeout

```
Error: Analysis timed out
```

- Ensure audio is under 10 minutes
- Check CPU usage (analysis is parallel but intensive)
- For very complex songs, consider using a shorter section

### Gemini API Error

```
Error: Gemini evaluation failed, using MFCC fallback
```

This is expected behavior. The system automatically falls back to spectral similarity metrics when AI evaluation fails.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         Web UI (React)                         │
│                    SSE Stream + Audio Players                   │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FastAPI Backend                              │
│                    POST /api/sessions                           │
│                    GET /api/sessions/{id}/events (SSE)          │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Orchestrator (Google ADK)                    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │ Plan Agent  │  │ Exec Agent  │  │ Eval Agent  │             │
│  │ (Gemini 3)  │  │ (MCP Tools) │  │ (Gemini 3)  │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
└─────────────────────────────────────────────────────────────────┘
         │                   │                   │
         ▼                   ▼                   ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│ Analysis Tools  │  │  REAPER MCP     │  │  Gemini 3 API   │
│ demucs          │  │  batch_create   │  │  Audio Input    │
│ basic-pitch     │  │  batch_midi     │  │  (WAV)          │
│ madmom          │  │  render_audio   │  └─────────────────┘
│ librosa         │  └─────────────────┘
└─────────────────┘
```

## Key Files

| Path | Purpose |
|------|---------|
| `songclone/api/main.py` | FastAPI application entry |
| `songclone/orchestrator/main.py` | Agentic loop implementation |
| `songclone/orchestrator/prompts/` | Agent system prompts |
| `songclone/analysis/pipeline.py` | Audio analysis orchestration |
| `songclone/reaper_mcp/server.py` | MCP server for REAPER |
| `songclone/web/src/App.tsx` | Main React component |
| `songclone/web/src/hooks/useSSE.ts` | SSE subscription hook |

## Testing

```bash
# Run integration tests
pytest tests/integration/ -v

# Test analysis pipeline
pytest tests/integration/test_analysis_pipeline.py -v

# Test REAPER MCP (requires REAPER running)
pytest tests/integration/test_reaper_mcp.py -v
```

## Performance Notes

- **Analysis**: ~1-2 min for 3-min song (parallel execution)
- **Per Iteration**: ~20-30 sec (plan + execute + evaluate)
- **Full Loop**: ~3-5 min for 10 iterations on 3-min song
- **UI Latency**: <500ms event-to-display
