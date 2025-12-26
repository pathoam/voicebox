"""Retry decorator for API calls."""

import time
import logging
from functools import wraps
from typing import Callable, Type, Tuple, Any


def retry_once(
    max_retries: int = 1,
    delay: float = 1.0,
    retryable_exceptions: Tuple[Any, ...] = (Exception,),
) -> Callable:
    """
    Decorator to retry function calls once on failure.

    Args:
        max_retries: Number of retry attempts (default: 1)
        delay: Delay in seconds before retry (default: 1.0)
        retryable_exceptions: Exception types that trigger retry

    Returns:
        Decorator function
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            logger = logging.getLogger(func.__module__)
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        logger.warning(
                            f"{func.__name__} failed (attempt {attempt + 1}/{max_retries + 1}), "
                            f"retrying in {delay}s: {e}"
                        )
                        time.sleep(delay)

            logger.error(f"{func.__name__} failed after {max_retries} retries")
            raise last_exception

        return wrapper

    return decorator
