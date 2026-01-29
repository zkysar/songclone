"""SSE event schemas and broadcasting infrastructure."""

import asyncio
from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional, Union
from uuid import uuid4

from pydantic import BaseModel, Field


class TimestampedEvent(BaseModel):
    """Base class for all SSE events with automatic timestamps."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class PhaseType(str, Enum):
    ANALYSIS = "analysis"
    ITERATION = "iteration"


class EventStatus(str, Enum):
    STARTED = "started"
    COMPLETE = "complete"


class StepType(str, Enum):
    PLANNING = "planning"
    EXECUTION = "execution"
    EVALUATION = "evaluation"


class LogLevel(str, Enum):
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


class CompleteReason(str, Enum):
    THRESHOLD_REACHED = "threshold_reached"
    MAX_ITERATIONS = "max_iterations"
    CANCELLED = "cancelled"


class PhaseEvent(TimestampedEvent):
    type: Literal["phase"] = "phase"
    phase: PhaseType
    status: EventStatus
    data: Optional[Any] = None


class IterationEvent(TimestampedEvent):
    type: Literal["iteration"] = "iteration"
    number: int
    status: EventStatus


class StepEvent(TimestampedEvent):
    type: Literal["step"] = "step"
    step: StepType
    status: EventStatus
    data: Optional[Any] = None


class LogEvent(TimestampedEvent):
    type: Literal["log"] = "log"
    level: LogLevel
    message: str


class AudioEvent(TimestampedEvent):
    type: Literal["audio"] = "audio"
    iteration: int
    path: str


class HumanActionEvent(TimestampedEvent):
    type: Literal["human_action_required"] = "human_action_required"
    description: str = Field(..., description="What action is needed")
    reason: str = Field(..., description="Why automation failed")
    steps: list[str] = Field(..., description="Step-by-step instructions")


class PausedEvent(TimestampedEvent):
    type: Literal["paused"] = "paused"
    reason: str = Field(..., description="Why the session was paused")


class CompleteEvent(TimestampedEvent):
    type: Literal["complete"] = "complete"
    reason: CompleteReason
    iterations: int = Field(..., description="Total iterations completed")


class ErrorEvent(TimestampedEvent):
    type: Literal["error"] = "error"
    message: str
    recoverable: bool


class ReaperOperationType(str, Enum):
    CREATE_PROJECT = "create_project"
    BATCH_CREATE_TRACKS = "batch_create_tracks"
    BATCH_INSERT_MIDI = "batch_insert_midi"
    BATCH_SET_FX = "batch_set_fx"
    BATCH_SET_LEVELS = "batch_set_levels"
    RENDER_AUDIO = "render_audio"


class ReaperOperationEvent(TimestampedEvent):
    type: Literal["reaper_operation"] = "reaper_operation"
    operation: ReaperOperationType
    status: EventStatus
    details: Optional[dict[str, Any]] = None
    error: Optional[str] = None


class ToolCallEvent(TimestampedEvent):
    """ADK tool call event."""
    type: Literal["tool_call"] = "tool_call"
    tool: str
    call_id: str = Field(default_factory=lambda: str(uuid4())[:8])
    args: Optional[dict[str, Any]] = None


class ToolResponseEvent(TimestampedEvent):
    """ADK tool response event."""
    type: Literal["tool_response"] = "tool_response"
    tool: str
    call_id: str
    status: str
    result: Optional[dict[str, Any]] = None
    duration_ms: Optional[int] = None


class AgentResponseEvent(TimestampedEvent):
    """ADK agent final response."""
    type: Literal["agent_response"] = "agent_response"
    content: str


class AgentThinkingEvent(TimestampedEvent):
    """ADK agent thinking/reasoning event."""
    type: Literal["agent_thinking"] = "agent_thinking"
    content: str
    agent: str = "orchestrator"


class TraceUrlEvent(TimestampedEvent):
    """Langfuse trace URL for observability."""
    type: Literal["trace_url"] = "trace_url"
    url: str


SSEEvent = Union[
    PhaseEvent,
    IterationEvent,
    StepEvent,
    LogEvent,
    AudioEvent,
    HumanActionEvent,
    PausedEvent,
    CompleteEvent,
    ErrorEvent,
    ReaperOperationEvent,
    ToolCallEvent,
    ToolResponseEvent,
    AgentResponseEvent,
    AgentThinkingEvent,
    TraceUrlEvent,
]


class EventEmitter:
    """Async event emitter for SSE broadcasting to connected clients."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue[SSEEvent]]] = {}

    def subscribe(self, session_id: str) -> asyncio.Queue[SSEEvent]:
        """Subscribe to events for a session. Returns a queue to receive events."""
        if session_id not in self._subscribers:
            self._subscribers[session_id] = []
        queue: asyncio.Queue[SSEEvent] = asyncio.Queue()
        self._subscribers[session_id].append(queue)
        return queue

    def unsubscribe(self, session_id: str, queue: asyncio.Queue[SSEEvent]) -> None:
        """Unsubscribe from events for a session."""
        if session_id in self._subscribers:
            try:
                self._subscribers[session_id].remove(queue)
            except ValueError:
                pass
            if not self._subscribers[session_id]:
                del self._subscribers[session_id]

    async def emit(self, session_id: str, event: SSEEvent) -> None:
        """Emit an event to all subscribers of a session."""
        if session_id in self._subscribers:
            for queue in self._subscribers[session_id]:
                await queue.put(event)

    def emit_sync(self, session_id: str, event: SSEEvent) -> None:
        """Synchronous version for use in non-async contexts."""
        if session_id in self._subscribers:
            for queue in self._subscribers[session_id]:
                queue.put_nowait(event)


event_emitter = EventEmitter()
