"""File-based session management."""

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from songclone.api.schemas import (
    ConversationMessage,
    ConversationRole,
    Session,
    SessionStatus,
)

SESSIONS_DIR = Path("sessions")


def _ensure_sessions_dir() -> None:
    SESSIONS_DIR.mkdir(exist_ok=True)


def _session_path(session_id: str) -> Path:
    return SESSIONS_DIR / session_id


def _session_json_path(session_id: str) -> Path:
    return _session_path(session_id) / "session.json"


def create_session(
    max_iterations: int = 10,
    min_iterations: int = 5,
    quality_threshold: float = 0.8,
) -> Session:
    """Create a new session with a unique ID and initialize its directory."""
    _ensure_sessions_dir()

    session_id = str(uuid.uuid4())
    session_dir = _session_path(session_id)
    session_dir.mkdir(exist_ok=True)

    (session_dir / "iterations").mkdir(exist_ok=True)

    now = datetime.utcnow()
    session = Session(
        id=session_id,
        status=SessionStatus.UPLOADING,
        max_iterations=max_iterations,
        min_iterations=min_iterations,
        quality_threshold=quality_threshold,
        created_at=now,
        updated_at=now,
    )

    save_session(session)
    return session


def save_session(session: Session) -> None:
    """Save session state to JSON file."""
    session.updated_at = datetime.utcnow()
    session_file = _session_json_path(session.id)

    with open(session_file, "w") as f:
        f.write(session.model_dump_json(indent=2))


def load_session(session_id: str) -> Optional[Session]:
    """Load session from JSON file. Returns None if session doesn't exist."""
    session_file = _session_json_path(session_id)

    if not session_file.exists():
        return None

    with open(session_file) as f:
        data = json.load(f)

    return Session.model_validate(data)


def get_session_url(session_id: str, base_url: str = "http://localhost:5173") -> str:
    """Generate the URL to view/reconnect to a session."""
    return f"{base_url}?session={session_id}"


def get_original_audio_path(session_id: str) -> Path:
    """Get the path where original audio should be stored."""
    return _session_path(session_id) / "original.wav"


def get_iteration_dir(session_id: str, iteration_number: int) -> Path:
    """Get the directory for a specific iteration."""
    iteration_dir = _session_path(session_id) / "iterations" / f"{iteration_number:03d}"
    iteration_dir.mkdir(parents=True, exist_ok=True)
    return iteration_dir


def get_iteration_render_path(session_id: str, iteration_number: int) -> Path:
    """Get the path for an iteration's rendered audio."""
    return get_iteration_dir(session_id, iteration_number) / "render.wav"


def session_exists(session_id: str) -> bool:
    """Check if a session exists."""
    return _session_json_path(session_id).exists()


def list_sessions() -> list[str]:
    """List all session IDs."""
    _ensure_sessions_dir()
    return [
        d.name for d in SESSIONS_DIR.iterdir()
        if d.is_dir() and (d / "session.json").exists()
    ]


def append_conversation_message(
    session_id: str,
    role: ConversationRole,
    content: Optional[str] = None,
    tool_name: Optional[str] = None,
    tool_args: Optional[dict[str, Any]] = None,
    tool_result: Optional[Any] = None,
    iteration: Optional[int] = None,
) -> None:
    """Append a message to the session's conversation history."""
    session = load_session(session_id)
    if not session:
        return

    message = ConversationMessage(
        role=role,
        timestamp=datetime.utcnow(),
        content=content,
        tool_name=tool_name,
        tool_args=tool_args,
        tool_result=tool_result,
        iteration=iteration,
    )
    session.conversation_history.append(message)
    save_session(session)


def log_user_message(session_id: str, content: str, iteration: Optional[int] = None) -> None:
    """Log a user message sent to the LLM."""
    append_conversation_message(
        session_id,
        role=ConversationRole.USER,
        content=content,
        iteration=iteration,
    )


def log_assistant_response(session_id: str, content: str, iteration: Optional[int] = None) -> None:
    """Log an assistant response from the LLM."""
    append_conversation_message(
        session_id,
        role=ConversationRole.ASSISTANT,
        content=content,
        iteration=iteration,
    )


def log_tool_call(
    session_id: str,
    tool_name: str,
    tool_args: dict[str, Any],
    iteration: Optional[int] = None,
) -> None:
    """Log a tool call made by the LLM."""
    append_conversation_message(
        session_id,
        role=ConversationRole.TOOL_CALL,
        tool_name=tool_name,
        tool_args=tool_args,
        iteration=iteration,
    )


def log_tool_response(
    session_id: str,
    tool_name: str,
    tool_result: Any,
    iteration: Optional[int] = None,
) -> None:
    """Log a tool response returned to the LLM."""
    append_conversation_message(
        session_id,
        role=ConversationRole.TOOL_RESPONSE,
        tool_name=tool_name,
        tool_result=tool_result,
        iteration=iteration,
    )
