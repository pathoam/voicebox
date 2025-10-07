from typing import Optional, List, Tuple, Dict, Any
import time
import pyperclip
import base64
import io
from pynput.keyboard import Controller as KeyboardController, Key

try:
    from PIL import Image, ImageGrab
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False


class TextInserter:
    """Cross-platform text insertion using keyboard simulation and clipboard."""
    
    def __init__(self, platform_name: Optional[str] = None):
        self.keyboard = KeyboardController()
        self._original_clipboard: Optional[str] = None
        self.platform = (platform_name or self._detect_platform()).lower()
        
    def insert_text(self, text: str, method: str = "auto") -> bool:
        """
        Insert text at the current cursor position.
        
        Args:
            text: Text to insert
            method: Insertion method - "auto", "clipboard", or "typing"
            
        Returns:
            True if successful, False otherwise
        """
        print(f"🔤 TextInserter.insert_text() called with: '{text}' (method: {method})")
        print(f"🔤 Method parameter type: {type(method)}")
        print(f"🔤 Method parameter repr: {repr(method)}")
        
        if not text or not text.strip():
            print("No text to insert")
            return False
            
        text = text.strip()
        
        print(f"🔤 Before force, method is: {method}")
        
        # TEMPORARILY FORCE CLIPBOARD METHOD TO DEBUG  
        method = "clipboard"
        print(f"🔤 After force, method is: {method}")
        
        # if method == "auto":
        #     # Choose method based on text length and complexity
        #     if len(text) > 100 or '\n' in text:
        #         method = "clipboard"
        #     else:
        #         method = "typing"
                
        print(f"🔤 Using insertion method: {method}")
        
        try:
            # FORCE CLIPBOARD TEST - BYPASS ALL LOGIC
            print("🔤 FORCING CLIPBOARD METHOD")
            result = self._insert_via_clipboard(text)
            
            # if method == "clipboard":
            #     result = self._insert_via_clipboard(text)
            # else:
            #     result = self._insert_via_typing(text)
            
            print(f"🔤 Insertion result: {result}")
            return result
                
        except Exception as e:
            print(f"Error inserting text: {e}")
            return False
            
    def _insert_via_clipboard(self, text: str) -> bool:
        """Insert text using clipboard and paste operation."""
        try:
            print(f"📋 Starting clipboard insertion for: '{text}'")
            
            # Save current clipboard content
            try:
                self._original_clipboard = pyperclip.paste()
                print(f"📋 Saved original clipboard: '{self._original_clipboard[:50]}...'")
            except Exception:
                self._original_clipboard = None
                print("📋 No original clipboard to save")
                
            # Set text to clipboard
            print(f"📋 Copying to clipboard: '{text}'")
            pyperclip.copy(text)
            
            # Small delay to ensure clipboard is set
            time.sleep(0.1)
            
            # Paste using platform-appropriate shortcut
            print("📋 Performing paste shortcut...")
            self._perform_paste_shortcut()
            print("📋 Paste shortcut completed")
            
            # Small delay before restoring clipboard
            time.sleep(0.2)
            
            # Restore original clipboard content
            if self._original_clipboard is not None:
                try:
                    print(f"📋 Restoring original clipboard")
                    pyperclip.copy(self._original_clipboard)
                except Exception:
                    pass
            
            print("📋 Clipboard insertion completed successfully")
            return True
            
        except Exception as e:
            print(f"Clipboard insertion failed: {e}")
            return False
            
    def _insert_via_typing(self, text: str) -> bool:
        """Insert text by simulating typing."""
        try:
            print(f"⌨️ About to type: '{text}'")
            # Type the text character by character
            self.keyboard.type(text)
            print(f"⌨️ Finished typing: '{text}'")
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
    
    def get_clipboard_type_and_content(self) -> Dict[str, Any]:
        """
        Detect clipboard content type and return structured data.
        
        Returns:
            Dict with 'type' ('text', 'image', 'none') and 'content' fields
        """
        print("📋 Checking clipboard content type...")
        
        # Try to get image from clipboard first (if PIL is available)
        if PILLOW_AVAILABLE:
            try:
                print("📋 PIL is available, attempting to grab clipboard image...")
                img = ImageGrab.grabclipboard()
                print(f"📋 ImageGrab.grabclipboard() returned: {type(img)} - {repr(img)}")
                
                if img and isinstance(img, Image.Image):
                    print(f"📋 Found image in clipboard: {img.size} {img.mode}")
                    return {
                        "type": "image",
                        "content": img,
                        "info": f"{img.size[0]}x{img.size[1]} {img.mode}"
                    }
                elif img is not None:
                    print(f"📋 Clipboard contains non-image data: {type(img)}")
                else:
                    print("📋 No image data in clipboard")
            except Exception as e:
                print(f"📋 Error checking clipboard for image: {e}")
                import traceback
                traceback.print_exc()
        else:
            print("📋 PIL not available for image clipboard detection")
        
        # Try to get text from clipboard
        try:
            text = pyperclip.paste()
            if text and text.strip():
                print(f"📋 Found text in clipboard: {len(text)} characters")
                return {
                    "type": "text", 
                    "content": text,
                    "info": f"{len(text)} chars"
                }
        except Exception as e:
            print(f"📋 Error reading clipboard text: {e}")
        
        print("📋 No usable content found in clipboard")
        return {"type": "none", "content": None, "info": "empty"}
    
    def image_to_base64(self, img: 'Image.Image') -> str:
        """Convert PIL Image to base64 string."""
        if not PILLOW_AVAILABLE:
            raise RuntimeError("PIL not available for image processing")
        
        # Convert to RGB if necessary (for JPEG compatibility)
        if img.mode in ('RGBA', 'LA', 'P'):
            img = img.convert('RGB')
        
        # Save to bytes buffer
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=85)
        img_bytes = buffer.getvalue()
        
        # Encode to base64
        return base64.b64encode(img_bytes).decode('utf-8')

    def _detect_platform(self) -> str:
        """Fallback platform detection if not provided."""
        import platform as _platform

        system = _platform.system().lower()
        if system.startswith("win"):
            return "windows"
        if system.startswith("darwin") or system == "mac" or system == "macos":
            return "macos"
        if system.startswith("linux"):
            return "linux"
        return "unknown"

    def _perform_paste_shortcut(self) -> None:
        """Send the appropriate paste shortcut for the current platform."""
        modifiers, key = self._get_paste_shortcut()
        print(f"⌨️ Paste shortcut: {[str(m) for m in modifiers]} + {key}")

        try:
            print(f"⌨️ Pressing modifiers: {modifiers}")
            for modifier in modifiers:
                print(f"  ⌨️ Press {modifier}")
                self.keyboard.press(modifier)

            print(f"⌨️ Press key: {key}")
            self.keyboard.press(key)
            print(f"⌨️ Release key: {key}")
            self.keyboard.release(key)

        finally:
            print(f"⌨️ Releasing modifiers")
            for modifier in reversed(modifiers):
                print(f"  ⌨️ Release {modifier}")
                self.keyboard.release(modifier)

    def _get_paste_shortcut(self) -> Tuple[List[Key], str]:
        """Return modifier keys and primary key for paste action."""
        if self.platform == "macos":
            return ([Key.cmd], 'v')
        if self.platform == "windows":
            return ([Key.ctrl], 'v')
        if self.platform == "linux":
            print("🐧 Linux detected - using Ctrl+Shift+V for terminal compatibility")
            return ([Key.ctrl, Key.shift], 'v')
        return ([Key.ctrl], 'v')
