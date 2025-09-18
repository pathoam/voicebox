from typing import Optional
import time
import pyperclip
from pynput.keyboard import Controller as KeyboardController, Key


class TextInserter:
    """Cross-platform text insertion using keyboard simulation and clipboard."""
    
    def __init__(self):
        self.keyboard = KeyboardController()
        self._original_clipboard: Optional[str] = None
        
    def insert_text(self, text: str, method: str = "auto") -> bool:
        """
        Insert text at the current cursor position.
        
        Args:
            text: Text to insert
            method: Insertion method - "auto", "clipboard", or "typing"
            
        Returns:
            True if successful, False otherwise
        """
        if not text or not text.strip():
            print("No text to insert")
            return False
            
        text = text.strip()
        
        if method == "auto":
            # Choose method based on text length and complexity
            if len(text) > 100 or '\n' in text:
                method = "clipboard"
            else:
                method = "typing"
                
        try:
            if method == "clipboard":
                return self._insert_via_clipboard(text)
            else:
                return self._insert_via_typing(text)
                
        except Exception as e:
            print(f"Error inserting text: {e}")
            return False
            
    def _insert_via_clipboard(self, text: str) -> bool:
        """Insert text using clipboard and paste operation."""
        try:
            # Save current clipboard content
            try:
                self._original_clipboard = pyperclip.paste()
            except Exception:
                self._original_clipboard = None
                
            # Set text to clipboard
            pyperclip.copy(text)
            
            # Small delay to ensure clipboard is set
            time.sleep(0.1)
            
            # Paste using Ctrl+Shift+V (works in terminals and most apps)
            self.keyboard.press(Key.ctrl)
            self.keyboard.press(Key.shift)
            self.keyboard.press('v')
            self.keyboard.release('v')
            self.keyboard.release(Key.shift)
            self.keyboard.release(Key.ctrl)
            
            # Small delay before restoring clipboard
            time.sleep(0.2)
            
            # Restore original clipboard content
            if self._original_clipboard is not None:
                try:
                    pyperclip.copy(self._original_clipboard)
                except Exception:
                    pass
                    
            return True
            
        except Exception as e:
            print(f"Clipboard insertion failed: {e}")
            return False
            
    def _insert_via_typing(self, text: str) -> bool:
        """Insert text by simulating typing."""
        try:
            # Type the text character by character
            self.keyboard.type(text)
            return True
            
        except Exception as e:
            print(f"Typing insertion failed: {e}")
            return False
            
    def insert_text_with_formatting(self, text: str) -> bool:
        """
        Insert text with basic formatting cleanup.
        
        Args:
            text: Text to insert with formatting
            
        Returns:
            True if successful, False otherwise
        """
        # Clean up the text
        cleaned_text = self._clean_text(text)
        return self.insert_text(cleaned_text)
        
    def _clean_text(self, text: str) -> str:
        """Clean up transcribed text for better insertion."""
        if not text:
            return ""
            
        # Remove extra whitespace
        text = ' '.join(text.split())
        
        # Capitalize first letter
        if text and text[0].islower():
            text = text[0].upper() + text[1:]
            
        # Ensure sentence ends with period if it doesn't have punctuation
        if text and text[-1].isalpha():
            text += "."
            
        return text
        
    def test_insertion(self) -> bool:
        """Test if text insertion is working."""
        test_text = "VoiceBox test"
        print("Testing text insertion in 3 seconds...")
        time.sleep(3)
        return self.insert_text(test_text)
        
    def get_clipboard_content(self) -> str:
        """Get current clipboard content for debugging."""
        try:
            return pyperclip.paste()
        except Exception as e:
            print(f"Error reading clipboard: {e}")
            return ""