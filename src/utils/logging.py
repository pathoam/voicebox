"""Centralized logging system for VoiceBox."""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


# Global debug mode flag
DEBUG_MODE = False


def set_debug_mode(enabled: bool) -> None:
    """
    Enable/disable debug mode globally.

    Args:
        enabled: Whether to enable debug mode
    """
    global DEBUG_MODE
    DEBUG_MODE = enabled


def get_logger(name: str) -> logging.Logger:
    """
    Get configured logger for a module.

    Args:
        name: Logger name (usually __name__)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # Only configure once to avoid duplicate handlers
    if not logger.handlers:
        # Set base level
        logger.setLevel(logging.DEBUG if DEBUG_MODE else logging.INFO)
        logger.propagate = False

        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.ERROR if not DEBUG_MODE else logging.DEBUG)

        # File handler
        log_dir = Path.home() / ".config" / "VoiceBox"
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_dir / "voicebox.log",
            maxBytes=5 * 1024 * 1024,  # 5MB
            backupCount=3,
        )
        file_handler.setLevel(logging.WARNING if not DEBUG_MODE else logging.DEBUG)

        # Formatter: [timestamp] LEVEL message
        formatter = logging.Formatter(
            "[%(asctime)s] %(levelname)s %(message)s", datefmt="%H:%M:%S"
        )
        console_handler.setFormatter(formatter)
        file_handler.setFormatter(formatter)

        logger.addHandler(console_handler)
        logger.addHandler(file_handler)

    return logger
