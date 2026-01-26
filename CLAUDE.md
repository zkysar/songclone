# SongClone Development Guidelines

Auto-generated from feature plans. Last updated: 2026-01-26

## Active Technologies

- **Python 3.11+**: Backend, orchestrator, analysis pipeline, REAPER MCP
- **TypeScript 5.x**: Frontend (React + Vite)
- **Storage**: File-based only (WAV files, JSON state) - no database

## Project Structure

```text
songclone/
├── analysis/          # Audio analysis pipeline (demucs, basic-pitch, madmom)
├── reaper_mcp/        # Custom MCP server for REAPER batch operations
├── orchestrator/      # Google ADK agents (planning, execution, evaluation)
│   └── prompts/       # Agent system prompts (separate files, not inline)
├── api/               # FastAPI backend
└── web/               # React frontend
    └── src/
        ├── components/
        ├── hooks/
        └── types/

tests/
└── integration/       # Integration tests only (per constitution)
```

## Commands

```bash
# Backend
source venv/bin/activate
uvicorn songclone.api.main:app --reload --port 8000

# Frontend
cd songclone/web && npm run dev

# Tests
pytest tests/integration/ -v

# Linting
ruff check songclone/
```

## Code Style

- **Type hints required** on all function signatures
- **No "what" comments** - code must be self-evident
- **Comments only for "why"** (non-obvious decisions)
- **Pydantic schemas** for all inter-agent communication
- **Typed responses** from all tools (never just "success")

## Constitution Principles

See `.specify/memory/constitution.md` for full details:

1. **Stack**: Google ADK + Gemini 3 Pro + file-based state
2. **Agent Design**: Single responsibility, Pydantic schemas, prompts in `/orchestrator/prompts/`
3. **MCP & Tools**: Batch ops, typed responses, idempotent, REAPER state verification
4. **Error Handling**: SSE on errors, VST fallback, parallel analysis, max 3 retries
5. **Human-in-the-Loop**: 3 alternatives before help, `human_action_required` events
6. **Hackathon**: UI-demonstrable, no premature optimization, skip auth/persistence
7. **Gemini 3**: `thinking_level="high"` for planning, WAV audio, <4000 token prompts

## Current Feature

**Branch**: `001-songclone`
**Spec**: `specs/001-songclone/spec.md`
**Plan**: `specs/001-songclone/plan.md`

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
