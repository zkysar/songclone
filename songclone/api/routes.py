"""API routes for SongClone."""

import asyncio
import logging
import shutil
from pathlib import Path
from typing import AsyncGenerator

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse

from songclone.api.events import (
    AgentResponseEvent,
    HumanActionEvent,
    LogEvent,
    LogLevel,
    PausedEvent,
    SSEEvent,
    ToolCallEvent,
    ToolResponseEvent,
    TraceUrlEvent,
    event_emitter,
)
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
from songclone.orchestrator.adk_runner import (
    cancel_adk_session,
    create_adk_session,
    run_orchestrator_with_adk,
    send_message_to_agent,
)

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
    audio: UploadFile = File(...),
    max_iterations: int = Form(10),
    min_iterations: int = Form(5),
    quality_threshold: float = Form(0.8),
) -> SessionCreated:
    """
    Create a new recreation session.

    Upload an audio file (WAV or MP3, max 10 minutes) to start analysis.
    """
    print("=== CREATE_NEW_SESSION CALLED ===", flush=True)
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

    print(f"=== ABOUT TO CREATE TASK for {session.id} ===", flush=True)
    logger.info(f"Scheduling analysis task for session {session.id}")
    asyncio.create_task(
        run_analysis(
            session.id,
            audio_path,
            max_iterations,
            quality_threshold,
        )
    )
    print(f"=== TASK CREATED for {session.id} ===", flush=True)
    logger.info(f"Analysis task scheduled for session {session.id}")

    return SessionCreated(
        session_id=session.id,
        session_url=get_session_url(session.id),
    )


async def run_analysis(
    session_id: str,
    audio_path: Path,
    max_iterations: int = 10,
    quality_threshold: float = 0.8,
) -> None:
    """Background task to run analysis pipeline and start ADK orchestration."""
    print(f"=== RUN_ANALYSIS STARTED for {session_id} ===", flush=True)
    logger.info(f"run_analysis started for session {session_id}")

    print(f"=== Loading session {session_id} ===", flush=True)
    session = load_session(session_id)
    if not session:
        print(f"=== SESSION NOT FOUND {session_id} ===", flush=True)
        logger.error(f"Session {session_id} not found for analysis")
        return

    print(f"=== Session loaded, starting try block ===", flush=True)
    try:
        output_dir = audio_path.parent / "analysis"
        print(f"=== Calling analyze_song for {audio_path} ===", flush=True)
        logger.info(f"Starting analyze_song for {audio_path}")

        song_spec = await analyze_song(
            audio_path=audio_path,
            output_dir=output_dir,
            session_id=session_id,
        )
        print(f"=== analyze_song RETURNED ===", flush=True)

        session = load_session(session_id)
        if session:
            session.song_spec = song_spec
            save_session(session)
            print(f"=== Session saved with song_spec ===", flush=True)

            # Start ADK orchestration
            print(f"=== Starting ADK orchestration ===", flush=True)
            logger.info(f"Starting ADK orchestration for session {session_id}")
            await create_adk_session(session_id)
            print(f"=== ADK session created ===", flush=True)

            render_dir = audio_path.parent / "renders"
            render_dir.mkdir(exist_ok=True)
            print(f"=== Calling run_orchestrator_with_adk ===", flush=True)

            async for event in run_orchestrator_with_adk(
                session_id=session_id,
                song_spec_json=song_spec.model_dump_json(),
                original_audio_path=str(audio_path),
                output_dir=str(render_dir),
                max_iterations=max_iterations,
                quality_threshold=quality_threshold,
            ):
                # Forward ADK events to SSE
                event_type = event.get("type")
                if event_type == "tool_call":
                    await event_emitter.emit(
                        session_id,
                        ToolCallEvent(tool=event.get("tool", ""), args=event.get("args")),
                    )
                elif event_type == "tool_response":
                    await event_emitter.emit(
                        session_id,
                        ToolResponseEvent(
                            tool=event.get("tool", ""),
                            call_id=event.get("call_id", "unknown"),
                            status=event.get("status", ""),
                        ),
                    )
                elif event_type == "agent_response":
                    await event_emitter.emit(
                        session_id,
                        AgentResponseEvent(content=event.get("content", "")),
                    )
                elif event_type == "error":
                    await event_emitter.emit(
                        session_id,
                        LogEvent(level=LogLevel.ERROR, message=event.get("message", "")),
                    )
                elif event_type == "log":
                    level_str = event.get("level", "info")
                    level = LogLevel.ERROR if level_str == "error" else (
                        LogLevel.WARN if level_str == "warn" else LogLevel.INFO
                    )
                    await event_emitter.emit(
                        session_id,
                        LogEvent(level=level, message=event.get("message", "")),
                    )
                elif event_type == "trace_url":
                    await event_emitter.emit(
                        session_id,
                        TraceUrlEvent(url=event.get("url", "")),
                    )
                elif event_type == "human_action_required":
                    await event_emitter.emit(
                        session_id,
                        HumanActionEvent(
                            description=event.get("description", "Action required"),
                            reason=event.get("reason", ""),
                            steps=event.get("steps", []),
                        ),
                    )
                elif event_type == "paused":
                    session = load_session(session_id)
                    if session:
                        session.status = SessionStatus.PAUSED
                        session.pause_context = {"reason": event.get("reason", "")}
                        save_session(session)
                    await event_emitter.emit(
                        session_id,
                        PausedEvent(reason=event.get("reason", "")),
                    )
                    logger.info(f"Session {session_id} paused: {event.get('reason')}")
                    return

            logger.info(f"ADK orchestration complete for session {session_id}")

    except Exception as e:
        import traceback
        logger.error(f"Analysis failed for session {session_id}: {e}")
        logger.error(traceback.format_exc())
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

    # Cancel ADK session and emit events
    await cancel_adk_session(session_id)

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

    # Resume via ADK message
    background_tasks.add_task(resume_adk_session, session_id)

    # Return current state (will be updated by background task)
    return session


async def resume_adk_session(session_id: str) -> None:
    """Resume ADK session by sending retry message."""
    logger.info(f"Resuming ADK session {session_id}")

    session = load_session(session_id)
    if session:
        session.status = SessionStatus.ITERATING
        session.pause_context = None
        save_session(session)

    resume_message = """REAPER is now ready. Please retry execute_plan with the same plan.
Continue the song recreation workflow from where you left off."""

    async for event in send_message_to_agent(session_id, resume_message):
        event_type = event.get("type")

        if event_type == "tool_call":
            await event_emitter.emit(
                session_id,
                ToolCallEvent(tool=event.get("tool", ""), args=event.get("args")),
            )
        elif event_type == "tool_response":
            await event_emitter.emit(
                session_id,
                ToolResponseEvent(
                    tool=event.get("tool", ""),
                    call_id=event.get("call_id", "unknown"),
                    status=event.get("status", ""),
                ),
            )
        elif event_type == "agent_response":
            await event_emitter.emit(
                session_id,
                AgentResponseEvent(content=event.get("content", "")),
            )
        elif event_type == "error":
            await event_emitter.emit(
                session_id,
                LogEvent(level=LogLevel.ERROR, message=event.get("message", "")),
            )
        elif event_type == "log":
            level_str = event.get("level", "info")
            level = LogLevel.ERROR if level_str == "error" else (
                LogLevel.WARN if level_str == "warn" else LogLevel.INFO
            )
            await event_emitter.emit(
                session_id,
                LogEvent(level=level, message=event.get("message", "")),
            )
        elif event_type == "trace_url":
            await event_emitter.emit(
                session_id,
                TraceUrlEvent(url=event.get("url", "")),
            )
        elif event_type == "human_action_required":
            await event_emitter.emit(
                session_id,
                HumanActionEvent(
                    description=event.get("description", "Action required"),
                    reason=event.get("reason", ""),
                    steps=event.get("steps", []),
                ),
            )
        elif event_type == "paused":
            # Another REAPER failure during resume
            session = load_session(session_id)
            if session:
                session.status = SessionStatus.PAUSED
                session.pause_context = {"reason": event.get("reason", "")}
                save_session(session)
            await event_emitter.emit(
                session_id,
                PausedEvent(reason=event.get("reason", "")),
            )
            logger.info(f"Session {session_id} paused again: {event.get('reason')}")
            return

    logger.info(f"ADK session {session_id} resumed successfully")


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
