"""Pydantic schemas for API request/response models."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from songclone.analysis.schemas import SongSpec
from songclone.orchestrator.schemas import EvaluationResult, ExecutionPlan


class SessionStatus(str, Enum):
    UPLOADING = "uploading"
    ANALYZING = "analyzing"
    ITERATING = "iterating"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class IterationStatus(str, Enum):
    PLANNING = "planning"
    EXECUTING = "executing"
    EVALUATING = "evaluating"
    COMPLETED = "completed"
    FAILED = "failed"


class ConversationRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    TOOL_CALL = "tool_call"
    TOOL_RESPONSE = "tool_response"


class ConversationMessage(BaseModel):
    role: ConversationRole
    timestamp: datetime
    content: Optional[str] = None
    tool_name: Optional[str] = None
    tool_args: Optional[dict[str, Any]] = None
    tool_result: Optional[Any] = None
    iteration: Optional[int] = None


class Iteration(BaseModel):
    number: int = Field(..., ge=1, description="Iteration number (1-indexed)")
    plan: ExecutionPlan
    render_path: Optional[str] = Field(None, description="Path to rendered WAV")
    evaluation: Optional[EvaluationResult] = None
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: IterationStatus


class Session(BaseModel):
    id: str = Field(..., description="UUID session identifier")
    status: SessionStatus
    original_audio_path: Optional[str] = None
    song_spec: Optional[SongSpec] = None
    iterations: list[Iteration] = Field(default_factory=list)
    current_iteration: int = Field(0, ge=0)
    max_iterations: int = Field(10, ge=1, le=20)
    min_iterations: int = Field(5, ge=1, le=20)
    quality_threshold: float = Field(0.8, ge=0.0, le=1.0)
    created_at: datetime
    updated_at: datetime
    error: Optional[str] = None
    pause_context: Optional[dict[str, Any]] = None
    conversation_history: list[ConversationMessage] = Field(default_factory=list)


class SessionCreated(BaseModel):
    session_id: str
    session_url: str = Field(..., description="URL to view session (for reconnection)")


class ErrorResponse(BaseModel):
    error: str
    message: str
