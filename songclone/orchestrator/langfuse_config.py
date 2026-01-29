"""Langfuse observability configuration for ADK agents.

This module initializes Langfuse tracing and instruments Google ADK
to automatically capture all agent operations.
"""

import logging
import os

logger = logging.getLogger(__name__)

# Suppress noisy context errors from async generator cleanup
logging.getLogger("opentelemetry.context").setLevel(logging.CRITICAL)
logging.getLogger("langfuse").setLevel(logging.ERROR)

_initialized = False
_langfuse_client = None


def init_langfuse() -> bool:
    """
    Initialize Langfuse and instrument Google ADK.

    Returns:
        True if initialization succeeded, False otherwise.
    """
    global _initialized, _langfuse_client

    if _initialized:
        return True

    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")

    if not public_key or not secret_key:
        logger.warning("Langfuse keys not configured - tracing disabled")
        return False

    try:
        from langfuse import get_client
        from openinference.instrumentation.google_adk import GoogleADKInstrumentor

        _langfuse_client = get_client()

        if _langfuse_client.auth_check():
            logger.info("Langfuse connection verified")
        else:
            logger.warning("Langfuse auth check failed")
            return False

        GoogleADKInstrumentor().instrument()
        logger.info("Google ADK instrumented for Langfuse tracing")

        _initialized = True
        return True

    except ImportError as e:
        logger.warning(f"Langfuse dependencies not installed: {e}")
        return False
    except Exception as e:
        logger.error(f"Failed to initialize Langfuse: {e}")
        return False


def get_trace_url() -> str | None:
    """
    Get the URL for the current trace.

    Returns:
        Trace URL if available, None otherwise.
    """
    if not _initialized or not _langfuse_client:
        return None

    try:
        return _langfuse_client.get_trace_url()
    except Exception:
        return None


def get_trace_id() -> str | None:
    """
    Get the current trace ID.

    Returns:
        Trace ID if available, None otherwise.
    """
    if not _initialized or not _langfuse_client:
        return None

    try:
        return _langfuse_client.get_current_trace_id()
    except Exception:
        return None


def print_trace_link(name: str = "trace") -> str | None:
    """
    Print and return the current Langfuse trace URL.

    Args:
        name: Label for the trace link in output.

    Returns:
        Trace URL if available, None otherwise.
    """
    url = get_trace_url()
    if url:
        print(f"\n🔗 Langfuse [{name}]: {url}\n")
    return url


def start_trace(name: str, session_id: str | None = None):
    """
    Start a new root trace as a context manager.

    In Langfuse v3, traces are implicitly created by the first root span.
    We use start_as_current_observation with as_type="span" to create
    a root span that will establish the trace.

    Args:
        name: Name for the trace.
        session_id: Optional session ID to associate with the trace.

    Returns:
        Context manager for the trace.
    """
    from contextlib import contextmanager, nullcontext

    if not _initialized or not _langfuse_client:
        return nullcontext()

    from langfuse import propagate_attributes

    @contextmanager
    def _trace_context():
        propagate_ctx = propagate_attributes(session_id=session_id) if session_id else nullcontext()
        with propagate_ctx:
            with _langfuse_client.start_as_current_observation(
                as_type="span",
                name=name,
            ) as span:
                yield span

    return _trace_context()


def start_span(name: str):
    """
    Start a new span under the current trace as a context manager.

    Args:
        name: Name for the span.

    Returns:
        Context manager for the span.
    """
    from contextlib import nullcontext

    if not _initialized or not _langfuse_client:
        return nullcontext()

    return _langfuse_client.start_as_current_observation(as_type="span", name=name)
