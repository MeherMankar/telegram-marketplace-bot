#!/usr/bin/env python3
"""Test script for enhanced session converter"""

import asyncio
import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.utils.UniversalSessionConverter import UniversalSessionConverter

async def test_converter():
    """Test the enhanced session converter"""
    
    print("🔧 Testing Universal Session Converter")
    print("=" * 50)
    
    # Test 1: Session type detection
    print("\n1. Testing session type detection:")
    
    test_cases = [
        ("test.session", "Expected: telethon_session or pyrogram_session"),
        ("test.json", "Expected: json_session"),
        ("/path/to/tdata", "Expected: tdata (if tdata folder exists)"),
        ("BQAAABcAAAAAaGVsbG8gd29ybGQ", "Expected: telethon_string"),
        ('{"session_string": "test"}', "Expected: json_session"),
        (b"binary_data", "Expected: session_bytes")
    ]
    
    for test_input, expected in test_cases:
        detected = UniversalSessionConverter._detect_session_type(test_input)
        print(f"  Input: {str(test_input)[:30]}... -> {detected} ({expected})")
    
    # Test 2: Session info without conversion
    print("\n2. Testing session info extraction:")
    
    info_result = UniversalSessionConverter.get_session_info("nonexistent.session")
    print(f"  Session info result: {info_result}")
    
    # Test 3: Test conversion with invalid data (should handle gracefully)
    print("\n3. Testing error handling:")
    
    try:
        result = await UniversalSessionConverter.convert_session("invalid_data", "unknown_type")
        print(f"  Invalid conversion result: {result}")
    except Exception as e:
        print(f"  Exception handled: {e}")
    
    print("\n✅ Enhanced session converter tests completed!")
    print("\nFeatures added:")
    print("• Auto-detection of session formats")
    print("• Enhanced TData parsing with multiple strategies")
    print("• Better Pyrogram session conversion")
    print("• JSON session format support")
    print("• Improved error handling")
    print("• Session info extraction without full conversion")

if __name__ == "__main__":
    asyncio.run(test_converter())