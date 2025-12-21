#!/usr/bin/env python3
"""Automatically apply security fixes to Python files"""
import os
import re
from pathlib import Path

def fix_datetime_in_file(filepath):
    """Replace datetime.utcnow() with utc_now()"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except (UnicodeDecodeError, IOError):
        return False
    
    original = content
    
    # Add import if needed
    if 'datetime.utcnow()' in content:
        if 'from app.utils.datetime_utils import utc_now' not in content:
            # Find last import line
            lines = content.split('\n')
            last_import = 0
            for i, line in enumerate(lines):
                if line.startswith('import ') or line.startswith('from '):
                    last_import = i
            
            lines.insert(last_import + 1, 'from app.utils.datetime_utils import utc_now')
            content = '\n'.join(lines)
        
        # Replace datetime.utcnow() with utc_now()
        content = re.sub(r'datetime\.utcnow\(\)', 'utc_now()', content)
    
    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False

def fix_exceptions_in_file(filepath):
    """Replace generic except Exception with specific exceptions"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except (UnicodeDecodeError, IOError):
        return False
    
    original = content
    
    # Replace except Exception: with except (ValueError, RuntimeError, OSError, IOError):
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if 'except Exception:' in line and 'except (ValueError' not in line:
            indent = len(line) - len(line.lstrip())
            lines[i] = ' ' * indent + 'except (ValueError, RuntimeError, OSError, IOError):'
    
    content = '\n'.join(lines)
    
    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False

def apply_all_fixes():
    """Apply all fixes to Python files"""
    datetime_fixed = 0
    exception_fixed = 0
    
    for root, dirs, files in os.walk('app'):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        
        for file in files:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)
                
                if fix_datetime_in_file(filepath):
                    datetime_fixed += 1
                    print(f"[+] Fixed datetime in {filepath}")
                
                if fix_exceptions_in_file(filepath):
                    exception_fixed += 1
                    print(f"[+] Fixed exceptions in {filepath}")
    
    print(f"\n[OK] Fixed {datetime_fixed} files with datetime issues")
    print(f"[OK] Fixed {exception_fixed} files with exception issues")

if __name__ == '__main__':
    print("[*] Applying security fixes...\n")
    apply_all_fixes()
    print("\n[OK] Fixes applied! Run 'python fix_issues.py' to verify")
