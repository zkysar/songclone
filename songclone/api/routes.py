"""API routes for SongClone."""

import asyncio
import logging
import shutil
from pathlib import Path
from typing import AsyncGenerator

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse

from songclone.api.events import event_emitter, SSEEvent
from songclone.api.schemas import (
    ErrorResponse,
    Session,
    SessionCreated,
    SessionStatus,
)
from songclone.api.session import (
    create_session,
    get_iteration_render_path,
    get_original_audio_path,
    get_session_url,
    load_session,
    save_session,
    session_exists,
)
from songclone.analysis.pipeline import analyze_song
from songclone.orchestrator.main import run_recreation_loop, cancel_session as cancel_recreation

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_AUDIO_DURATION_SECONDS = 600
ALLOWED_AUDIO_TYPES = {"audio/wav", "audio/mpeg", "audio/mp3", "audio/x-wav"}


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}


@router.post("/sessions", response_model=SessionCreated, status_code=201)
async def create_new_session(
    background_tasks: BackgroundTasks,
    audio: UploadFile = File(...),
    max_iterations: int = Form(10),
    min_iterations: int = Form(5),
    quality_threshold: float = Form(0.8),
) -> SessionCreated:
    """
    Create a new recreation session.

    Upload an audio file (WAV or MP3, max 10 minutes) to start analysis.
    """
    if audio.content_type and audio.content_type not in ALLOWED_AUDIO_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid audio format. Allowed: WAV, MP3. Got: {audio.content_type}",
        )

    if not 1 <= max_iterations <= 20:
        raise HTTPException(
            status_code=400,
            detail="max_iterations must be between 1 and 20",
        )

    if not 1 <= min_iterations <= 20:
        raise HTTPException(
            status_code=400,
            detail="min_iterations must be between 1 and 20",
        )

    if min_iterations > max_iterations:
        raise HTTPException(
            status_code=400,
            detail="min_iterations cannot exceed max_iterations",
        )

    if not 0.0 <= quality_threshold <= 1.0:
        raise HTTPException(
            status_code=400,
            detail="quality_threshold must be between 0.0 and 1.0",
        )

    session = create_session(
        max_iterations=max_iterations,
        min_iterations=min_iterations,
        quality_threshold=quality_threshold,
    )

    audio_path = get_original_audio_path(session.id)

    try:
        with open(audio_path, "wb") as f:
            content = await audio.read()
            f.write(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save audio: {e}")

    session.original_audio_path = str(audio_path)
    session.status = SessionStatus.ANALYZING
    save_session(session)

    background_tasks.add_task(run_analysis, session.id, audio_path)

    return SessionCreated(
        session_id=session.id,
        session_url=get_session_url(session.id),
    )


async def run_analysis(session_id: str, audio_path: Path) -> None:
    """Background task to run analysis pipeline and auto-start recreation."""
    session = load_session(session_id)
    if not session:
        logger.error(f"Session {session_id} not found for analysis")
        return

    try:
        output_dir = audio_path.parent / "analysis"

        song_spec = await analyze_song(
            audio_path=audio_path,
            output_dir=output_dir,
            session_id=session_id,
        )

        session = load_session(session_id)
        if session:
            session.song_spec = song_spec
            save_session(session)

            # Auto-start recreation loop after analysis completes
            await run_recreation_loop(session)

    except Exception as e:
        logger.error(f"Analysis failed for session {session_id}: {e}")
        session = load_session(session_id)
        if session:
            session.status = SessionStatus.FAILED
            session.error = str(e)
            save_session(session)


@router.get("/sessions/{session_id}", response_model=Session)
async def get_session(session_id: str) -> Session:
    """Get session details."""
    session = load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.get("/sessions/{session_id}/events")
async def stream_events(session_id: str) -> EventSourceResponse:
    """
    Stream session events via Server-Sent Events.

    Connect to receive real-time updates during analysis and iteration.
    """
    if not session_exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found")

    async def event_generator() -> AsyncGenerator[dict[str, str], None]:
        queue = event_emitter.subscribe(session_id)

        try:
            while True:
                try:
                    event: SSEEvent = await asyncio.wait_for(queue.get(), timeout=30)
                    yield {
                        "event": event.type,
                        "data": event.model_dump_json(),
                    }
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
        finally:
            event_emitter.unsubscribe(session_id, queue)

    return EventSourceResponse(event_generator())


@router.post("/sessions/{session_id}/cancel", response_model=Session)
async def cancel_session_endpoint(session_id: str) -> Session:
    """Cancel session and preserve completed iterations."""
    session = load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.status not in [SessionStatus.ANALYZING, SessionStatus.ITERATING]:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot cancel session in {session.status} state",
        )

    # Use orchestrator's cancel to properly emit events
    await cancel_recreation(session)

    # Reload to get updated state
    session = load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return session


@router.post("/sessions/{session_id}/resume", response_model=Session)
async def resume_session(
    session_id: str,
    background_tasks: BackgroundTasks,
) -> Session:
    """Resume paused session after human action completed."""
    session = load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.status != SessionStatus.PAUSED:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot resume session in {session.status} state",
        )

    # Resume recreation in background
    background_tasks.add_task(run_recreation_loop, session)

    # Return current state (will be updated by background task)
    return session


@router.get("/sessions/{session_id}/audio/original")
async def get_original_audio(session_id: str) -> FileResponse:
    """Get original uploaded audio."""
    session = load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    audio_path = get_original_audio_path(session_id)
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="Original audio not found")

    return FileResponse(
        path=str(audio_path),
        media_type="audio/wav",
        filename="original.wav",
    )


@router.get("/sessions/{session_id}/audio/iteration/{iteration}")
async def get_iteration_audio(session_id: str, iteration: int) -> FileResponse:
    """Get rendered audio for an iteration."""
    session = load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if iteration < 1 or iteration > len(session.iterations):
        raise HTTPException(status_code=404, detail="Iteration not found")

    render_path = get_iteration_render_path(session_id, iteration)
    if not render_path.exists():
        raise HTTPException(status_code=404, detail="Iteration audio not found")

    return FileResponse(
        path=str(render_path),
        media_type="audio/wav",
        filename=f"iteration_{iteration}.wav",
    )


@router.get("/sessions/{session_id}/download")
async def download_best_result(session_id: str) -> FileResponse:
    """Download the best recreation as WAV."""
    session = load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if not session.iterations:
        raise HTTPException(status_code=404, detail="No iterations completed")

    best_iteration = max(
        session.iterations,
        key=lambda it: it.evaluation.total_score if it.evaluation else 0,
    )

    render_path = get_iteration_render_path(session_id, best_iteration.number)
    if not render_path.exists():
        raise HTTPException(status_code=404, detail="Best iteration audio not found")

    return FileResponse(
        path=str(render_path),
        media_type="audio/wav",
        filename="songclone_best.wav",
        headers={"Content-Disposition": 'attachment; filename="songclone_best.wav"'},
    )
