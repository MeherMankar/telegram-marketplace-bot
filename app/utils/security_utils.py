"""Security utilities for path validation and input sanitization"""
from pathlib import Path
from typing import Optional
import os
from html import escape

def validate_path(user_path: str, base_dir: str) -> str:
    """Validate and sanitize path to prevent traversal attacks"""
    try:
        base_resolved = Path(base_dir).resolve()
        user_resolved = (base_resolved / Path(user_path).name).resolve()
        
        if not str(user_resolved).startswith(str(base_resolved)):
            raise ValueError("Path traversal detected")
        
        return str(user_resolved)
    except (ValueError, RuntimeError) as e:
        raise ValueError(f"Invalid path: {e}")

def safe_join_path(base_dir: str, *parts: str) -> str:
    """Safely join path components"""
    base_resolved = Path(base_dir).resolve()
    result = base_resolved
    
    for part in parts:
        safe_part = Path(part).name
        result = result / safe_part
        
        if not str(result.resolve()).startswith(str(base_resolved)):
            raise ValueError("Path traversal detected")
    
    return str(result.resolve())

def sanitize_message(text: str) -> str:
    """Sanitize message to prevent XSS"""
    if not isinstance(text, str):
        return str(text)
    return escape(text)

def get_safe_filename(filename: str) -> str:
    """Get safe filename without path traversal"""
    return Path(filename).name

def validate_input(value: str, max_length: int = 1000, pattern: Optional[str] = None) -> str:
    """Validate and sanitize user input"""
    if not isinstance(value, str):
        raise ValueError("Input must be string")
    
    if len(value) > max_length:
        raise ValueError(f"Input exceeds max length of {max_length}")
    
    if pattern:
        import re
        if not re.match(pattern, value):
            raise ValueError("Input does not match required pattern")
    
    return sanitize_message(value)
