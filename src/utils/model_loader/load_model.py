import json
import hashlib
from typing import Dict, Any, Union, Type

from .chat_openai import ChatOpenAI
from .chat_gemini import ChatGoogleGenerativeAI

# Global cache for model instances
_model_cache: Dict[str, Any] = {}

def _get_model(**config) -> Union[ChatOpenAI, ChatGoogleGenerativeAI]:
    """
    Get model instance with caching support.
    
    If model name has been loaded before, return cached client instance.
    Otherwise, create new instance and cache it.
    
    Args:
        **config: Model configuration parameters
        
    Returns:
        Model instance (cached or newly created)
    """
    # Create cache key from configuration
    cache_key = _create_cache_key(config)
    
    # Check if model instance already exists in cache
    if cache_key in _model_cache:
        print(f"Using cached model instance for: {config.get('model', 'unknown')}")
        return _model_cache[cache_key]
    
    # Create new model instance if not in cache
    print(f"Creating new model instance for: {config.get('model', 'unknown')}")
    model_instance = _create_model_instance(**config)
    
    # Cache the new instance
    _model_cache[cache_key] = model_instance
    
    return model_instance

def _create_cache_key(config: Dict[str, Any]) -> str:
    """
    Create a unique cache key from model configuration.
    
    Args:
        config: Model configuration dictionary
        
    Returns:
        str: Unique cache key for the configuration
    """
    # Extract key parameters that identify a unique model instance
    key_params = {
        "model": config.get("model", ""),
    }
    
    # Create a hash from the key parameters for security and consistency
    key_string = json.dumps(key_params, sort_keys=True)
    return hashlib.md5(key_string.encode()).hexdigest()

def _create_model_instance(**config):
    """
    Create a new model instance based on configuration.
    
    Args:
        config: Model configuration dictionary
        
    Returns:
        Model instance
    """
    model_name = config.get("model", "")
    provider = config.get("provider", "")
    base_url = config.get("base_url", "")
    api_key = config.get("api_key", "")
    enable_thinking = config.get("enable_thinking", False)
    
    # Gemini models - return shared client
    if model_name in ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"]:
        return ChatGoogleGenerativeAI(
            api_key=api_key,
            model=model_name,
            stream_usage=True,
            # harm_block_threshold=HarmBlockThreshold(
            #     threshold=config.get("harm_block_threshold", 0.5),
            #     categories=[
            #         HarmCategory.HATE_SPEECH,
            #         HarmCategory.HARASSMENT,
            #         HarmCategory.DANGEROUS_CONTENT,
            #     ]
            # )
        )
    
    # OpenAI compatible server
    elif provider == "openai-compatible-server":
        if not enable_thinking:
            extra_body = {
                "chat_template_kwargs": {
                    "enable_thinking": enable_thinking
                }
            }
        else:
            extra_body = None
        return ChatOpenAI(
            base_url=base_url,
            api_key=api_key,
            model=model_name,
            stream_usage=True,
            default_headers={
                "App-Code": config.get("app_code", ""),
            },
            extra_body=extra_body,
            provider=provider
        )
    
    # OpenAI models
    else:
        return ChatOpenAI(
            base_url=base_url,
            api_key=api_key,
            model=model_name,
            stream_usage=True
        )

def clear_model_cache():
    """
    Clear the model cache. Useful for testing or memory management.
    """
    global _model_cache
    _model_cache.clear()
    print("Model cache cleared")

def get_cached_models_count() -> int:
    """
    Get the number of cached model instances.
    
    Returns:
        int: Number of cached models
    """
    return len(_model_cache)