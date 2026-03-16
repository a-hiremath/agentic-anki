"""Retry logic for transient API failures."""

from __future__ import annotations

import functools
import logging
import time
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

# HTTP status codes / exception types that are transient
_TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}


def with_retry(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
) -> Callable[[F], F]:
    """Decorator that retries a function on transient API errors."""

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            delay = initial_delay
            last_exc: Exception | None = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    if not _is_transient(exc):
                        raise
                    last_exc = exc
                    if attempt < max_retries:
                        logger.warning(
                            "Transient error (attempt %d/%d): %s. Retrying in %.1fs",
                            attempt + 1,
                            max_retries,
                            exc,
                            delay,
                        )
                        time.sleep(delay)
                        delay *= backoff_factor
            raise last_exc  # type: ignore[misc]

        return wrapper  # type: ignore[return-value]

    return decorator


def _is_transient(exc: Exception) -> bool:
    """Determine if an exception represents a transient API failure."""
    # anthropic SDK raises specific exception types
    exc_type = type(exc).__name__
    if exc_type in ("RateLimitError", "InternalServerError", "APITimeoutError"):
        return True
    # Check for HTTP status code in the exception
    status = getattr(exc, "status_code", None)
    if status in _TRANSIENT_STATUS_CODES:
        return True
    return False
