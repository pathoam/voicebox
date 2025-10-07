"""Command processing with LLM integration."""

import json
import requests
from typing import Optional, Dict, Any, List
from datetime import datetime
import re


class CommandProcessor:
    """Processes commands using built-in handlers or LLM."""
    
    def __init__(self, 
                 openrouter_api_key: Optional[str] = None,
                 local_llm_endpoint: Optional[str] = None,
                 model: str = "meta-llama/llama-3.2-3b-instruct:free"):
        """
        Initialize command processor.
        
        Args:
            openrouter_api_key: API key for OpenRouter
            local_llm_endpoint: Endpoint for local LLM (e.g., vLLM, Ollama)
            model: Model to use for OpenRouter
        """
        self.openrouter_api_key = openrouter_api_key
        self.local_llm_endpoint = local_llm_endpoint
        self.model = model
        self.timeout = 30
        
        # Track models that don't support system messages
        self.no_system_models = set()
        
        # Built-in command handlers
        self.built_in_commands = {
            "time": self._handle_time,
            "date": self._handle_date,
            "help": self._handle_help,
        }
        
    def process(self, command: str) -> Dict[str, Any]:
        """
        Process a command and return response.
        
        Args:
            command: Command text to process
            
        Returns:
            Dict with 'success', 'response', and optional 'error'
        """
        if not command:
            return {"success": False, "error": "No command provided"}
            
        # Check for built-in commands
        for keyword, handler in self.built_in_commands.items():
            if command.lower().startswith(keyword):
                return handler(command)
                
        # Otherwise, send to LLM
        return self._process_with_llm(command)
    
    def process_with_clipboard(self, command: str, clipboard_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a command with clipboard context.
        
        Args:
            command: Command text to process
            clipboard_data: Clipboard content from text_inserter.get_clipboard_type_and_content()
            
        Returns:
            Dict with 'success', 'response', and optional 'error'
        """
        if not command:
            return {"success": False, "error": "No command provided"}
        
        print(f"🤖 Processing command with clipboard: {repr(command)}")
        print(f"📋 Clipboard type: {clipboard_data.get('type')}, info: {clipboard_data.get('info')}")
        
        # Try local endpoint first
        if self.local_llm_endpoint:
            result = self._query_local_llm_with_clipboard(command, clipboard_data)
            if result["success"]:
                return result
                
        # Fall back to OpenRouter
        if self.openrouter_api_key:
            result = self._query_openrouter_with_clipboard(command, clipboard_data)
            return result  # Return the actual result, whether success or failure
                
        return {
            "success": False,
            "error": "No OpenRouter API key configured."
        }
        
    def _process_with_llm(self, command: str) -> Dict[str, Any]:
        """Process command using LLM."""
        # Try local endpoint first
        if self.local_llm_endpoint:
            result = self._query_local_llm(command)
            if result["success"]:
                return result
                
        # Fall back to OpenRouter
        if self.openrouter_api_key:
            result = self._query_openrouter(command)
            return result  # Return the actual result, whether success or failure
                
        return {
            "success": False,
            "error": "No OpenRouter API key configured."
        }
        
    def _query_local_llm(self, command: str) -> Dict[str, Any]:
        """Query local LLM endpoint (vLLM, Ollama, etc.)."""
        if not self.local_llm_endpoint:
            return {"success": False, "error": "No local LLM endpoint configured"}
            
        try:
            # Try OpenAI-compatible endpoint first
            response = requests.post(
                f"{self.local_llm_endpoint}/v1/chat/completions",
                json={
                    "model": "default",  # Most local servers use "default"
                    "messages": [
                        {"role": "system", "content": "You are a helpful assistant. Give ONLY the direct answer with absolutely NO preamble, introduction, or repetition of the question. Do not say 'Here is', 'Here are', 'The answer is', 'The image shows', or ANY prefacing text. Start immediately with the raw answer content only. Use only plain text with no formatting, LaTeX, markdown, asterisks, or special symbols. Be extremely brief and direct."},
                        {"role": "user", "content": command}
                    ],
                    "max_tokens": 200,  # Shorter responses
                    "temperature": 0.7
                },
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                data = response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                print(f"🤖 Local LLM raw response: {repr(content)}")
                if not content or not content.strip():
                    print("⚠️ Empty content from local LLM")
                    return {"success": False, "error": "Empty response from local LLM"}
                return {"success": True, "response": content}
            
            # Try Ollama format
            response = requests.post(
                f"{self.local_llm_endpoint}/api/generate",
                json={
                    "model": "llama3.2",  # Common default
                    "prompt": command,
                    "stream": False
                },
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                data = response.json()
                return {"success": True, "response": data.get("response", "")}
                
        except requests.RequestException as e:
            return {"success": False, "error": f"Local LLM error: {str(e)}"}
            
        return {"success": False, "error": "Failed to query local LLM"}
        
    def _query_openrouter(self, command: str) -> Dict[str, Any]:
        """Query OpenRouter API."""
        if not self.openrouter_api_key:
            return {"success": False, "error": "No OpenRouter API key configured"}
        
        # Check if this model is known to not support system messages
        if self.model in self.no_system_models:
            print(f"🤖 Model {self.model} known to not support system messages, using direct approach")
            return self._query_openrouter_no_system(command)
            
        try:
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant. Give ONLY the direct answer with absolutely NO preamble, introduction, or repetition of the question. Do not say 'Here is', 'Here are', 'The answer is', 'The image shows', or ANY prefacing text. Start immediately with the raw answer content only. Use only plain text with no formatting, LaTeX, markdown, asterisks, or special symbols. Be extremely brief and direct."},
                    {"role": "user", "content": command}
                ],
                "max_tokens": 200,  # Shorter responses
                "temperature": 0.7
            }
            print(f"🤖 OpenRouter request - Model: {self.model}, Command: {repr(command)}")
            
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.openrouter_api_key}",
                    "HTTP-Referer": "https://github.com/voicebox",  # Optional
                    "X-Title": "VoiceBox",  # Optional
                    "Content-Type": "application/json"
                },
                json=payload,
                timeout=self.timeout
            )
            
            print(f"🤖 OpenRouter response status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"🤖 OpenRouter response data: {data}")
                message = data.get("choices", [{}])[0].get("message", {})
                content = message.get("content", "")
                
                # Some models (like Qwen) put response in reasoning field
                if not content or not content.strip():
                    reasoning = message.get("reasoning", "")
                    if reasoning and reasoning.strip():
                        print(f"🤖 Found response in reasoning field: {repr(reasoning)}")
                        content = reasoning
                
                print(f"🤖 OpenRouter final response: {repr(content)}")
                if not content or not content.strip():
                    print("⚠️ Empty content from OpenRouter")
                    return {"success": False, "error": "Empty response from OpenRouter"}
                return {"success": True, "response": content}
            else:
                try:
                    error_data = response.json()
                    print(f"🤖 OpenRouter error response: {error_data}")
                    error_msg = error_data.get("error", {}).get("message", "Unknown error")
                    
                    # Check if the error is about system messages not being supported
                    error_lower = error_msg.lower()
                    raw_error = str(error_data.get("error", {}).get("metadata", {}).get("raw", "")).lower()
                    
                    if ("instruction" in error_lower or "system" in error_lower or 
                        "developer instruction" in raw_error or "instruction is not enabled" in raw_error):
                        print(f"🔄 Model {self.model} doesn't support system messages, remembering and retrying...")
                        self.no_system_models.add(self.model)
                        return self._query_openrouter_no_system(command)
                        
                except:
                    error_msg = f"HTTP {response.status_code}: {response.text}"
                return {"success": False, "error": f"OpenRouter error: {error_msg}"}
                
        except requests.RequestException as e:
            return {"success": False, "error": f"OpenRouter request failed: {str(e)}"}
    
    def _query_openrouter_no_system(self, command: str) -> Dict[str, Any]:
        """Query OpenRouter API without system message for models that don't support it."""
        try:
            # Embed the instructions directly in the user message
            user_prompt = f"Give ONLY the direct answer with no preamble or repetition of the question. Do not say 'Here is', 'The answer is', or repeat any part of the question - just give the raw answer content: {command}"
            
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "user", "content": user_prompt}
                ],
                "max_tokens": 200,
                "temperature": 0.7
            }
            print(f"🤖 OpenRouter retry (no system) - Model: {self.model}")
            
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.openrouter_api_key}",
                    "HTTP-Referer": "https://github.com/voicebox",
                    "X-Title": "VoiceBox",
                    "Content-Type": "application/json"
                },
                json=payload,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                data = response.json()
                message = data.get("choices", [{}])[0].get("message", {})
                content = message.get("content", "")
                print(f"🤖 OpenRouter retry response: {repr(content)}")
                
                if not content or not content.strip():
                    return {"success": False, "error": "Empty response from OpenRouter (retry)"}
                return {"success": True, "response": content}
            else:
                return {"success": False, "error": f"OpenRouter retry failed: {response.status_code}"}
                
        except requests.RequestException as e:
            return {"success": False, "error": f"OpenRouter retry failed: {str(e)}"}
    
    def _query_openrouter_with_clipboard(self, command: str, clipboard_data: Dict[str, Any]) -> Dict[str, Any]:
        """Query OpenRouter API with clipboard context."""
        if not self.openrouter_api_key:
            return {"success": False, "error": "No OpenRouter API key configured"}
        
        # Check if this model is known to not support system messages
        use_system_message = self.model not in self.no_system_models
        
        try:
            if clipboard_data["type"] == "image":
                # Handle image clipboard content - let the API respond with its own error if vision isn't supported
                print(f"🖼️ Attempting to send image to model {self.model}")
                content = self._build_multimodal_content(command, clipboard_data, use_system_message)
                messages = [{"role": "user", "content": content}]
                
            elif clipboard_data["type"] == "text":
                # Handle text clipboard content
                if use_system_message:
                    enhanced_command = f"{command}\n\nClipboard content:\n{clipboard_data['content']}"
                    messages = [
                        {"role": "system", "content": "You are a helpful assistant. Give ONLY the direct answer with absolutely NO preamble, introduction, or repetition of the question. Do not say 'Here is', 'Here are', 'The answer is', 'The image shows', or ANY prefacing text. Start immediately with the raw answer content only. Use only plain text with no formatting, LaTeX, markdown, asterisks, or special symbols. Be extremely brief and direct."},
                        {"role": "user", "content": enhanced_command}
                    ]
                else:
                    enhanced_command = f"Give a direct, brief answer in plain text with no formatting: {command}\n\nClipboard content:\n{clipboard_data['content']}"
                    messages = [{"role": "user", "content": enhanced_command}]
            else:
                # No clipboard content, fall back to regular processing
                return self._query_openrouter(command)
            
            payload = {
                "model": self.model,
                "messages": messages,
                "max_tokens": 200,
                "temperature": 0.7
            }
            
            print(f"🤖 OpenRouter clipboard request - Model: {self.model}")
            print(f"📋 Content type: {clipboard_data['type']}")
            if clipboard_data["type"] == "image":
                print(f"📋 Image info: {clipboard_data.get('info', 'unknown')}")
            
            # Debug: log the payload structure (without the base64 data)
            if clipboard_data["type"] == "image":
                debug_payload = payload.copy()
                debug_payload["messages"] = [{"role": "user", "content": [
                    {"type": "text", "text": f"[COMMAND: {command}]"},
                    {"type": "image_url", "image_url": {"url": "[BASE64_IMAGE_DATA]"}}
                ]}]
                print(f"🤖 Sending multimodal payload structure: {debug_payload}")
            
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.openrouter_api_key}",
                    "HTTP-Referer": "https://github.com/voicebox",
                    "X-Title": "VoiceBox",
                    "Content-Type": "application/json"
                },
                json=payload,
                timeout=self.timeout
            )
            
            print(f"🤖 OpenRouter response status: {response.status_code}")
            if response.status_code == 404:
                # 404 often means the model doesn't support the request format
                if clipboard_data["type"] == "image":
                    print(f"⚠️ Model {self.model} likely doesn't support image input (404 error)")
                    return {"success": False, "error": f"Model {self.model} doesn't support image input"}
                else:
                    print(f"⚠️ 404 error - endpoint or model issue")
                    
            if response.status_code == 200:
                data = response.json()
                print(f"🤖 Full API response: {data}")
                message = data.get("choices", [{}])[0].get("message", {})
                content = message.get("content", "")
                
                # Some models (like Qwen) put response in reasoning field
                if not content or not content.strip():
                    reasoning = message.get("reasoning", "")
                    if reasoning and reasoning.strip():
                        print(f"🤖 Found response in reasoning field: {repr(reasoning)}")
                        content = reasoning
                
                print(f"🤖 OpenRouter clipboard response: {repr(content)}")
                if not content or not content.strip():
                    print(f"⚠️ Empty response - full message object: {message}")
                    return {"success": False, "error": "Empty response from OpenRouter"}
                return {"success": True, "response": content}
            else:
                try:
                    error_data = response.json()
                    error_msg = error_data.get("error", {}).get("message", "Unknown error")
                    
                    # Check if the error is about system messages not being supported
                    error_lower = error_msg.lower()
                    raw_error = str(error_data.get("error", {}).get("metadata", {}).get("raw", "")).lower()
                    
                    if ("instruction" in error_lower or "system" in error_lower or 
                        "developer instruction" in raw_error or "instruction is not enabled" in raw_error):
                        print(f"🔄 Model {self.model} doesn't support system messages, remembering and retrying...")
                        self.no_system_models.add(self.model)
                        return self._query_openrouter_with_clipboard(command, clipboard_data)
                        
                except:
                    error_msg = f"HTTP {response.status_code}: {response.text}"
                return {"success": False, "error": f"OpenRouter error: {error_msg}"}
                
        except requests.RequestException as e:
            return {"success": False, "error": f"OpenRouter request failed: {str(e)}"}
    
    def _query_local_llm_with_clipboard(self, command: str, clipboard_data: Dict[str, Any]) -> Dict[str, Any]:
        """Query local LLM with clipboard context."""
        # For now, local LLMs only support text context
        if clipboard_data["type"] == "text":
            enhanced_command = f"{command}\n\nClipboard content:\n{clipboard_data['content']}"
            return self._query_local_llm(enhanced_command)
        elif clipboard_data["type"] == "image":
            # Local LLMs typically don't support images yet
            return {"success": False, "error": "Local LLM doesn't support image input"}
        else:
            return self._query_local_llm(command)
    
    def _build_multimodal_content(self, command: str, clipboard_data: Dict[str, Any], use_system_message: bool) -> List[Dict[str, Any]]:
        """Build multimodal content array for OpenRouter API."""
        try:
            # Import PIL and image conversion locally
            import base64
            import io
            from PIL import Image
            
            img = clipboard_data["content"]
            print(f"🖼️ Processing image: {img.size} {img.mode}")
            
            # Resize image if too large (many APIs have size limits)
            max_size = 1024
            if max(img.size) > max_size:
                ratio = max_size / max(img.size)
                new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
                img = img.resize(new_size, Image.Resampling.LANCZOS)
                print(f"🖼️ Resized image to: {img.size}")
            
            # Convert to RGB if necessary (for JPEG compatibility)
            if img.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background
                print(f"🖼️ Converted to RGB from {clipboard_data['content'].mode}")
            
            # Save to bytes buffer with higher quality
            buffer = io.BytesIO()
            img.save(buffer, format='JPEG', quality=95, optimize=True)
            img_bytes = buffer.getvalue()
            print(f"🖼️ Image encoded: {len(img_bytes)} bytes")
            
            # Encode to base64
            img_b64 = base64.b64encode(img_bytes).decode('utf-8')
            
            if use_system_message:
                prompt_text = command
            else:
                prompt_text = f"Give ONLY the direct answer with no preamble or repetition of the question. Do not say 'Here is', 'The answer is', or repeat any part of the question - just give the raw answer content: {command}"
            
            return [
                {"type": "text", "text": prompt_text},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
            ]
        except Exception as e:
            print(f"🖼️ Image processing error: {e}")
            raise RuntimeError(f"Failed to process image: {e}")
            
    def _handle_time(self, command: str) -> Dict[str, Any]:
        """Handle time command."""
        current_time = datetime.now().strftime("%I:%M %p")
        return {"success": True, "response": f"The current time is {current_time}"}
        
    def _handle_date(self, command: str) -> Dict[str, Any]:
        """Handle date command."""
        current_date = datetime.now().strftime("%B %d, %Y")
        return {"success": True, "response": f"Today is {current_date}"}
        
    def _handle_help(self, command: str) -> Dict[str, Any]:
        """Handle help command."""
        help_text = """Available commands:
• time - Get current time
• date - Get current date
• Any other request - Processed by AI assistant

Examples:
"voicebox, what's the weather?"
"voicebox, create a shell script to delete all PNGs"
"voicebox, explain quantum computing"
"""
        return {"success": True, "response": help_text}
        
    def set_openrouter_key(self, api_key: str):
        """Update OpenRouter API key."""
        self.openrouter_api_key = api_key
        
    def set_local_endpoint(self, endpoint: str):
        """Update local LLM endpoint."""
        self.local_llm_endpoint = endpoint
        
    def set_model(self, model: str):
        """Update OpenRouter model."""
        self.model = model