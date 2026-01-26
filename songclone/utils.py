"""Shared utilities for SongClone."""

import asyncio
import functools
import logging
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RetryError(Exception):
    """Raised when all retries are exhausted."""

    def __init__(self, message: str, last_exception: Exception) -> None:
        super().__init__(message)
        self.last_exception = last_exception


def with_retry(
    max_retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Retry decorator for async functions.

    Per constitution IV: Maximum 3 retries per REAPER operation before surfacing error.

    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        delay: Initial delay between retries in seconds
        backoff: Multiplier for delay after each retry
        exceptions: Tuple of exception types to catch and retry
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception: Exception = Exception("No attempts made")
            current_delay = delay

            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        logger.warning(
                            f"Retry {attempt + 1}/{max_retries} for {func.__name__}: {e}"
                        )
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(
                            f"All {max_retries} retries exhausted for {func.__name__}: {e}"
                        )

            raise RetryError(
                f"Failed after {max_retries} attempts: {last_exception}",
                last_exception,
            )

        return wrapper  # type: ignore

    return decorator


def sync_with_retry(
    max_retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Synchronous version of retry decorator."""
    import time

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception: Exception = Exception("No attempts made")
            current_delay = delay

            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        logger.warning(
                            f"Retry {attempt + 1}/{max_retries} for {func.__name__}: {e}"
                        )
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(
                            f"All {max_retries} retries exhausted for {func.__name__}: {e}"
                        )

            raise RetryError(
                f"Failed after {max_retries} attempts: {last_exception}",
                last_exception,
            )

        return wrapper

    return decorator
