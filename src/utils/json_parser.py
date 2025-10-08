"""
Utility functions để parse JSON từ các dạng content khác nhau,
bao gồm cả JSON trực tiếp và JSON wrapped trong markdown blocks.
"""

import re
import json
import ast
import logging
from typing import Optional, Any, Type, TypeVar
from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar('T', bound=BaseModel)


def extract_json_from_content(content: str) -> str:
    """
    Extract JSON string từ content có thể chứa nhiều dạng formats khác nhau.
    
    Args:
        content: Raw content từ LLM response
        
    Returns:
        Cleaned JSON string ready for parsing
        
    Raises:
        ValueError: Nếu không tìm thấy valid JSON trong content
    """
    if not content or not content.strip():
        raise ValueError("Content is empty or None")
    
    content = content.strip()
    
    # Pattern 1: Markdown code blocks với json tag
    pattern_json_block = r'```json\s*(.*?)\s*```'
    match = re.search(pattern_json_block, content, re.DOTALL | re.IGNORECASE)
    if match:
        json_content = match.group(1).strip()
        if json_content:
            return _clean_json_string(json_content)
    
    # Pattern 2: Generic code blocks
    pattern_generic_block = r'```\s*(.*?)\s*```'
    match = re.search(pattern_generic_block, content, re.DOTALL)
    if match:
        json_content = match.group(1).strip()
        if json_content and _looks_like_json(json_content):
            return _clean_json_string(json_content)
    
    # Pattern 3: Inline code với backticks
    pattern_inline = r'`([^`]*)`'
    matches = re.findall(pattern_inline, content)
    for match_content in matches:
        if _looks_like_json(match_content.strip()):
            return _clean_json_string(match_content.strip())
    
    # Pattern 4: Try direct JSON parsing
    if _looks_like_json(content):
        return _clean_json_string(content)
    
    # Pattern 5: Tìm JSON object đầu tiên trong text
    pattern_json_object = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
    matches = re.findall(pattern_json_object, content, re.DOTALL)
    for match in matches:
        if _looks_like_json(match):
            return _clean_json_string(match)
    
    # Fallback: Return content gốc và để JSON parser handle
    return _clean_json_string(content)


def _looks_like_json(text: str) -> bool:
    """Check nếu text có vẻ giống JSON"""
    text = text.strip()
    return (
        (text.startswith('{') and text.endswith('}')) or
        (text.startswith('[') and text.endswith(']'))
    )


def _clean_json_string(json_str: str) -> str:
    """
    Clean JSON string để remove các lỗi common:
    - Comments
    - Trailing commas
    - Smart quote handling for mixed quote scenarios
    """
    json_str = json_str.strip()
    
    # Remove comments (// và /* */)
    json_str = re.sub(r'//.*?$', '', json_str, flags=re.MULTILINE)
    json_str = re.sub(r'/\*.*?\*/', '', json_str, flags=re.DOTALL)
    
    # Detect and handle quote style
    if _detect_single_quote_style(json_str):
        json_str = _swap_quotes(json_str)
    
    # Remove trailing commas
    json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
    
    return json_str.strip()


def parse_structured_response(content: str, schema: Type[T]) -> tuple[Optional[T], str]:
    """
    Parse content thành BaseModel object với comprehensive error handling.
    
    Args:
        content: Raw content từ LLM response
        schema: Pydantic BaseModel class để parse
        
    Returns:
        Tuple of (Parsed BaseModel object hoặc None, error message string)
    """
    if not content:
        error_msg = "Empty content provided for parsing"
        return None, error_msg
    
    errors = []  # Collect all error messages
    
    try:
        # Step 1: Extract JSON string
        try:
            json_str = extract_json_from_content(content)
        except Exception as extract_error:
            error_msg = f"Failed to extract JSON from content: {extract_error}"
            return None, error_msg
                
        # Step 2: Try standard json.loads first
        try:
            parsed_dict = json.loads(json_str)
            if "arguments" in parsed_dict and parsed_dict["arguments"]:
                parsed_dict = parsed_dict["arguments"]
            result = schema.model_validate(parsed_dict)
            return result, ""
        except Exception as e:
            errors.append(f"Standard JSON parsing: {e}")
                
            # Step 3: Try parsing as Python literal
            try:
                parsed_dict = ast.literal_eval(json_str)
                result = schema.model_validate(parsed_dict)
                return result, ""
            except Exception as e:
                errors.append(f"AST parsing: {e}")
                
                # Step 4: Try với additional cleaning
                try:
                    cleaned_again = _aggressive_json_clean(json_str)
                    parsed_dict = json.loads(cleaned_again)
                    result = schema.model_validate(parsed_dict)
                    return result, ""
                except Exception as final_error:
                    errors.append(f"Aggressive cleaning: {final_error}")
                    
                    # Compile all errors
                    error_msg = f"All parsing attempts failed. Errors: {'; '.join(errors)}. Original content: {content[:100]}..."
                    return None, error_msg
    
    except Exception as e:
        error_msg = f"Unexpected error in parse_structured_response: {e}. Content: {content[:100]}..."
        return None, error_msg

def _detect_single_quote_style(json_str: str) -> bool:
    """
    Detect if JSON uses single quotes for keys
    
    Args:
        json_str: JSON string to analyze
        
    Returns:
        True if JSON primarily uses single quotes, False otherwise
    """
    # Look for key patterns: 'key': or 'key' :
    single_quote_key_pattern = r"'\w+'\s*:"
    double_quote_key_pattern = r'"\w+"\s*:'
    
    single_matches = len(re.findall(single_quote_key_pattern, json_str))
    double_matches = len(re.findall(double_quote_key_pattern, json_str))
    
    # If we find more single-quoted keys than double-quoted keys
    # then this JSON uses single quote style
    return single_matches > double_matches


def _swap_quotes(json_str: str) -> str:
    """
    Swap single quotes with double quotes and vice versa using str.translate()
    
    Args:
        json_str: JSON string with mixed quotes
        
    Returns:
        JSON string with quotes swapped
    """
    # Create translation table for quote swapping - fastest method
    translation_table = str.maketrans({"'": '"', '"': "'"})
    return json_str.translate(translation_table)


def _aggressive_json_clean(json_str: str) -> str:
    """
    Aggressive cleaning for malformed JSON
    """
    # Remove any remaining comments
    json_str = re.sub(r'#.*?$', '', json_str, flags=re.MULTILINE)
    
    # Fix unquoted keys
    json_str = re.sub(r'(\w+)(\s*:)', r'"\1"\2', json_str)
    
    # Remove multiple trailing commas
    json_str = re.sub(r',+(\s*[}\]])', r'\1', json_str)
    
    # Fix boolean values (Python True/False -> JSON true/false)
    json_str = re.sub(r'\bTrue\b', 'true', json_str)
    json_str = re.sub(r'\bFalse\b', 'false', json_str)
    json_str = re.sub(r'\bNone\b', 'null', json_str)
    
    return json_str.strip()


def safe_parse_with_fallback(content: str, schema: Type[T], fallback_value: Any = None) -> tuple[T, str]:
    """
    Parse với fallback value nếu parsing fails.
    
    Args:
        content: Raw content
        schema: BaseModel schema
        fallback_value: Value để return nếu parsing fails
        
    Returns:
        Tuple of (Parsed object hoặc fallback_value, error message)
    """
    result, error_msg = parse_structured_response(content, schema)
    if result is not None:
        return result, error_msg
    
    if fallback_value is not None:
        if isinstance(fallback_value, dict):
            try:
                fallback_obj = schema.model_validate(fallback_value)
                return fallback_obj, f"Used fallback value due to parsing error: {error_msg}"
            except Exception as e:
                logger.error(f"Fallback validation failed: {e}")
                return fallback_value, f"Fallback validation failed: {e}. Original error: {error_msg}"
        return fallback_value, f"Used fallback value due to parsing error: {error_msg}"
    
    # Create empty instance nếu có thể
    try:
        empty_instance = schema()
        return empty_instance, f"Created empty instance due to parsing error: {error_msg}"
    except Exception as e:
        logger.error(f"Cannot create empty instance of {schema.__name__}: {e}")
        raise ValueError(f"Failed to parse content and no valid fallback available. Original error: {error_msg}")
