"""Dynamic error suggestion mapping.

Provides user-friendly suggestions based on exception types and context.
"""

import json
from typing import Dict, Any


ERROR_SUGGESTIONS: Dict[type, str] = {
    # Permission errors
    PermissionError: "Check file/directory permissions and ensure VoiceBox has access",
    # File system
    FileNotFoundError: "File not found - verify the file path",
    OSError: "System error occurred - check available disk space and permissions",
    # JSON parsing
    json.JSONDecodeError: "Configuration file is corrupted - reset to defaults",
}


def get_suggestion(exception: Exception, context: Any = None) -> str:
    """
    Get a dynamic suggestion based on exception type and context.

    Args:
        exception: The exception that occurred
        context: Optional context dictionary (operation_name, api_endpoint, etc.)

    Returns:
        User-friendly suggestion string
    """
    if context is None:
        context = {}
    exception_type = type(exception)

    # Check for exact type match
    if exception_type in ERROR_SUGGESTIONS:
        return ERROR_SUGGESTIONS[exception_type]

    # Check for base class matches
    for exc_type, suggestion in ERROR_SUGGESTIONS.items():
        if isinstance(exception, exc_type):
            return suggestion

    # Context-specific suggestions
    operation = context.get("operation", "")
    error_str = str(exception).lower()

    if "transcription" in operation.lower():
        if "quota" in error_str or "limit" in error_str:
            return "API quota exceeded - check billing or use local model"
        elif "rate limit" in error_str or "too many requests" in error_str:
            return "API rate limit - wait a moment and try again"
        elif "audio" in error_str:
            return "Check microphone and try speaking more clearly"

    elif "llm" in operation.lower() or "command" in operation.lower():
        if "vision" in error_str or "404" in error_str:
            return "Selected model doesn't support images - try a vision-capable model"
        elif "timeout" in error_str:
            return "LLM request timed out - try again or use a faster model"

    elif "insertion" in operation.lower():
        return "Ensure the target application has focus and try the 'typing' method"

    elif "audio" in operation.lower() or "recording" in operation.lower():
        if "device" in error_str:
            return "Check microphone connection and system audio settings"
        return "Ensure microphone permissions are granted"

    # Generic fallback
    return "Check configuration and try again, or enable debug mode for details"
