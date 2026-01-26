"""SSE event schemas and broadcasting infrastructure."""

import asyncio
from enum import Enum
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, Field


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


class PhaseEvent(BaseModel):
    type: Literal["phase"] = "phase"
    phase: PhaseType
    status: EventStatus
    data: Optional[Any] = None


class IterationEvent(BaseModel):
    type: Literal["iteration"] = "iteration"
    number: int
    status: EventStatus


class StepEvent(BaseModel):
    type: Literal["step"] = "step"
    step: StepType
    status: EventStatus
    data: Optional[Any] = None


class LogEvent(BaseModel):
    type: Literal["log"] = "log"
    level: LogLevel
    message: str


class AudioEvent(BaseModel):
    type: Literal["audio"] = "audio"
    iteration: int
    path: str


class HumanActionEvent(BaseModel):
    type: Literal["human_action_required"] = "human_action_required"
    description: str = Field(..., description="What action is needed")
    reason: str = Field(..., description="Why automation failed")
    steps: list[str] = Field(..., description="Step-by-step instructions")


class CompleteEvent(BaseModel):
    type: Literal["complete"] = "complete"
    reason: CompleteReason
    iterations: int = Field(..., description="Total iterations completed")


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    message: str
    recoverable: bool


SSEEvent = Union[
    PhaseEvent,
    IterationEvent,
    StepEvent,
    LogEvent,
    AudioEvent,
    HumanActionEvent,
    CompleteEvent,
    ErrorEvent,
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
