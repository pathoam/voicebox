"""OpenRouter model management and fetching."""

import json
import requests
from typing import List, Dict, Optional
from datetime import datetime, timedelta


class OpenRouterModels:
    """Fetches and manages OpenRouter model list."""
    
    MODELS_ENDPOINT = "https://openrouter.ai/api/v1/models"
    CACHE_DURATION = timedelta(hours=24)
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize model manager.
        
        Args:
            api_key: Optional OpenRouter API key for authenticated requests
        """
        self.api_key = api_key
        self._cache = None
        self._cache_time = None
        
    def fetch_models(self, force_refresh: bool = False) -> List[Dict[str, any]]:
        """
        Fetch available models from OpenRouter.
        
        Args:
            force_refresh: Force API call even if cache is valid
            
        Returns:
            List of model dictionaries with id, name, pricing, etc.
        """
        # Check cache first
        if not force_refresh and self._is_cache_valid():
            return self._cache
            
        try:
            headers = {
                "User-Agent": "VoiceBox/1.0"
            }
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
                print(f"Making authenticated request to OpenRouter...")
            else:
                print(f"Making unauthenticated request to OpenRouter...")
                
            print(f"Requesting: {self.MODELS_ENDPOINT}")
            response = requests.get(
                self.MODELS_ENDPOINT,
                headers=headers,
                timeout=15
            )
            
            print(f"Response status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                models = data.get("data", [])
                print(f"Received {len(models)} models from API")
                
                # Debug: print first few models and their capabilities
                for i, model in enumerate(models[:3]):
                    model_id = model.get('id', 'no-id')
                    model_name = model.get('name', 'no-name')
                    architecture = model.get('architecture', {})
                    modalities = architecture.get('modalities', []) if isinstance(architecture, dict) else []
                    print(f"Model {i}: {model_id} - {model_name}")
                    print(f"  Modalities: {modalities}")
                    if 'vision' in modalities:
                        print(f"  🎨 Vision-capable model detected!")
                
                # Cache the results
                self._cache = models
                self._cache_time = datetime.now()
                
                return models
            else:
                print(f"Failed to fetch models: {response.status_code}")
                print(f"Response body: {response.text[:200]}...")
                return self._get_default_models()
                
        except requests.RequestException as e:
            print(f"Error fetching models: {e}")
            return self._get_default_models()
            
    def get_model_list(self, force_refresh: bool = False) -> List[tuple[str, str, float]]:
        """
        Get simplified model list for UI.
        
        Returns:
            List of (id, display_name, price_per_million_tokens) tuples
        """
        models = self.fetch_models(force_refresh)
        
        model_list = []
        for model in models:
            model_id = model.get("id", "")
            name = model.get("name", model_id)
            
            # Check for vision capabilities
            architecture = model.get('architecture', {})
            modalities = architecture.get('modalities', []) if isinstance(architecture, dict) else []
            has_vision = 'vision' in modalities if isinstance(modalities, list) else False
            
            # Get pricing (already per token) - ensure numeric type
            pricing = model.get("pricing", {})
            prompt_price_raw = pricing.get("prompt", 0) if pricing else 0
            
            # Convert to float and handle potential string values
            # API returns price per token, convert to per million tokens
            try:
                prompt_price_per_token = float(prompt_price_raw) if prompt_price_raw else 0.0
                prompt_price = prompt_price_per_token * 1000000  # Convert to per million
            except (ValueError, TypeError):
                prompt_price = 0.0
            
            # Create display name with pricing and capabilities
            if prompt_price > 0:
                if prompt_price < 0.01:
                    price_suffix = "(Free)"
                else:
                    price_suffix = f"(${prompt_price:.2f}/M)"
            else:
                price_suffix = ""
                
            # Add vision indicator
            vision_suffix = " 🎨" if has_vision else ""
            
            display_name = f"{name} {price_suffix}{vision_suffix}".strip()
                
            model_list.append((model_id, display_name, prompt_price))
            
        # Sort by price (free first) then by name
        model_list.sort(key=lambda x: (x[2], x[1].lower()))
        
        return model_list
    
    def is_vision_capable(self, model_id: str) -> bool:
        """
        Check if a specific model supports vision/image input.
        
        Args:
            model_id: The model ID to check
            
        Returns:
            True if the model supports vision input
        """
        models = self.fetch_models()
        
        for model in models:
            if model.get("id") == model_id:
                architecture = model.get('architecture', {})
                if isinstance(architecture, dict):
                    # Check input_modalities (new API format)
                    input_modalities = architecture.get('input_modalities', [])
                    if isinstance(input_modalities, list) and 'image' in input_modalities:
                        return True
                    # Check modality field for combined format
                    modality = architecture.get('modality', '')
                    if 'image' in modality.lower():
                        return True
                    # Legacy: Check modalities field
                    modalities = architecture.get('modalities', [])
                    if isinstance(modalities, list) and 'vision' in modalities:
                        return True
        
        return False
        
    def get_free_models(self) -> List[tuple[str, str]]:
        """Get only free models."""
        all_models = self.get_model_list()
        return [(id, name) for id, name, price in all_models if price == 0]
        
    def get_popular_models(self) -> List[str]:
        """Get list of popular model IDs - only returns actual fetched models."""
        if not self._cache:
            return []
        
        # Return popular model IDs that actually exist in fetched data
        popular_patterns = [
            "meta-llama/llama-3.2",
            "openai/gpt-4o-mini", 
            "anthropic/claude-3.5-sonnet",
            "google/gemini",
            "microsoft/phi-3"
        ]
        
        popular_models = []
        for model in self._cache:
            model_id = model.get("id", "")
            for pattern in popular_patterns:
                if pattern in model_id.lower():
                    popular_models.append(model_id)
                    break
                    
        return popular_models[:8]  # Return top 8
        
    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid."""
        if not self._cache or not self._cache_time:
            return False
        return datetime.now() - self._cache_time < self.CACHE_DURATION
        
    def _get_default_models(self) -> List[Dict[str, any]]:
        """Return empty list when API is unavailable - no fake data."""
        return []
        
    def search_models(self, query: str) -> List[tuple[str, str, float]]:
        """
        Search models by name or ID.
        
        Args:
            query: Search query
            
        Returns:
            Filtered list of models matching query
        """
        query = query.lower()
        all_models = self.get_model_list()
        
        if not query:
            return all_models
            
        filtered = []
        for model_id, display_name, price in all_models:
            if query in model_id.lower() or query in display_name.lower():
                filtered.append((model_id, display_name, price))
                
        return filtered