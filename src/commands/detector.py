"""Command detection for transcribed text."""

import re
from typing import List, Optional, Tuple


class CommandDetector:
    """Detects and extracts commands from transcribed text."""
    
    def __init__(self, triggers: Optional[List[str]] = None):
        """
        Initialize command detector.
        
        Args:
            triggers: List of trigger words/phrases to detect commands
        """
        self.triggers = triggers or ["voicebox", "assistant", "computer"]
        # Build regex pattern for trigger detection
        self._build_trigger_pattern()
        
    def _build_trigger_pattern(self):
        """Build regex pattern for trigger detection."""
        # Create pattern that matches any trigger at the start
        # Case-insensitive, with optional punctuation after
        trigger_alternatives = "|".join(re.escape(t) for t in self.triggers)
        self.trigger_pattern = re.compile(
            f"^({trigger_alternatives})\\s*[,:]?\\s*(.+)",
            re.IGNORECASE
        )
        
    def is_command(self, text: str) -> bool:
        """
        Check if text starts with a command trigger.
        
        Args:
            text: Transcribed text to check
            
        Returns:
            True if text is a command
        """
        if not text:
            return False
            
        match = self.trigger_pattern.match(text.strip())
        return match is not None
        
    def extract_command(self, text: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Extract trigger and command from text.
        
        Args:
            text: Transcribed text containing command
            
        Returns:
            Tuple of (trigger, command) or (None, None) if not a command
        """
        if not text:
            return None, None
            
        match = self.trigger_pattern.match(text.strip())
        if match:
            trigger = match.group(1).lower()
            command = match.group(2).strip()
            return trigger, command
            
        return None, None
    
    def extract_command_with_clipboard(self, text: str) -> Tuple[Optional[str], Optional[str], bool]:
        """
        Extract trigger, command, and clipboard flag from text.
        
        Args:
            text: Transcribed text containing command
            
        Returns:
            Tuple of (trigger, command, has_clipboard) or (None, None, False) if not a command
        """
        trigger, command = self.extract_command(text)
        if not command:
            return None, None, False
        
        # Check for clipboard keyword (case-insensitive)
        has_clipboard = "clipboard" in command.lower()
        
        if has_clipboard:
            # Remove "clipboard" and surrounding context more intelligently
            # Handle patterns like "clipboard here", "this clipboard", "the clipboard"
            patterns = [
                r'\bthe\s+clipboard(\s+here)?\b',  # "the clipboard here" or "the clipboard"
                r'\bthis\s+clipboard\b',           # "this clipboard"  
                r'\bclipboard\s+here\b',           # "clipboard here"
                r'\bin\s+the\s+clipboard\b',       # "in the clipboard"
                r'\bfrom\s+clipboard\b',           # "from clipboard"
                r'\bclipboard\b'                   # just "clipboard"
            ]
            
            cleaned_command = command
            for pattern in patterns:
                cleaned_command = re.sub(pattern, '', cleaned_command, flags=re.IGNORECASE)
            
            # Clean up any double spaces, leading/trailing spaces, and fix grammar
            cleaned_command = re.sub(r'\s+', ' ', cleaned_command).strip()
            # Remove leading "that's" or "that is" if present after cleanup
            cleaned_command = re.sub(r'^(that\'s|that\s+is)\s+', '', cleaned_command, flags=re.IGNORECASE).strip()
            
            return trigger, cleaned_command, True
        
        return trigger, command, False
        
    def add_trigger(self, trigger: str):
        """Add a new trigger word."""
        if trigger and trigger.lower() not in [t.lower() for t in self.triggers]:
            self.triggers.append(trigger.lower())
            self._build_trigger_pattern()
            
    def remove_trigger(self, trigger: str):
        """Remove a trigger word."""
        self.triggers = [t for t in self.triggers if t.lower() != trigger.lower()]
        self._build_trigger_pattern()
        
    def get_triggers(self) -> List[str]:
        """Get current list of triggers."""
        return self.triggers.copy()