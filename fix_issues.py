#!/usr/bin/env python3
"""Script to help fix common security issues"""
import os
import re
from pathlib import Path

def scan_files():
    """Scan all Python files for issues"""
    issues = {
        'datetime': [],
        'exceptions': [],
        'hardcoded': []
    }
    
    for root, dirs, files in os.walk('app'):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        
        for file in files:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                except (UnicodeDecodeError, IOError):
                    continue
                
                if 'datetime.utcnow()' in content:
                    issues['datetime'].append(filepath)
                if 'except Exception:' in content:
                    issues['exceptions'].append(filepath)
                if 'password' in content.lower() and '=' in content:
                    issues['hardcoded'].append(filepath)
    
    return issues

if __name__ == '__main__':
    print("[*] Scanning for security issues...\n")
    
    issues = scan_files()
    
    print(f"[*] Files with naive datetime: {len(issues['datetime'])}")
    for f in issues['datetime'][:5]:
        print(f"    - {f}")
    
    print(f"\n[*] Files with generic exceptions: {len(issues['exceptions'])}")
    for f in issues['exceptions'][:5]:
        print(f"    - {f}")
    
    print(f"\n[*] Files with potential hardcoded values: {len(issues['hardcoded'])}")
    for f in issues['hardcoded'][:5]:
        print(f"    - {f}")
    
    print("\n[OK] Scan complete. Review SECURITY_CHECKLIST.md for remaining fixes")
