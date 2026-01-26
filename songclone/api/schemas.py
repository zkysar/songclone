"""Pydantic schemas for API request/response models."""

from datetime import datetime
from enum import Enum
from typing import Optional

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
    quality_threshold: float = Field(0.8, ge=0.0, le=1.0)
    created_at: datetime
    updated_at: datetime
    error: Optional[str] = None


class SessionCreated(BaseModel):
    session_id: str
    session_url: str = Field(..., description="URL to view session (for reconnection)")


class ErrorResponse(BaseModel):
    error: str
    message: str
