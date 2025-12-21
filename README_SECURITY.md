# Security Fixes Guide

## Quick Start

1. **Review Issues**: Read `SECURITY_SUMMARY.md`
2. **Check Checklist**: Follow `SECURITY_CHECKLIST.md`
3. **Use Templates**: Reference `FIXES_TEMPLATE.py`
4. **Scan Code**: Run `python fix_issues.py`

## Critical Fixes Applied

### ✅ Security Utilities Created
- `app/utils/security_utils.py` - Path validation, input sanitization
- `app/utils/datetime_utils.py` - Timezone-aware datetime

### ✅ Documentation Created
- `SECURITY_SUMMARY.md` - Overview of all issues
- `SECURITY_CHECKLIST.md` - Detailed checklist with line numbers
- `SECURITY_FIXES.md` - Implementation guide
- `FIXES_TEMPLATE.py` - Code examples for all fixes

## Manual Fixes Required

### Phase 1: Critical (Do First)
1. Remove hardcoded credentials from code
2. Add path validation to file operations
3. Fix generic exception handling

### Phase 2: High Priority
1. Sanitize user input in messages
2. Never log sensitive information
3. Add CSRF token validation

### Phase 3: Medium Priority
1. Replace `datetime.utcnow()` with `utc_now()`
2. Use context managers for file I/O
3. Update package dependencies

## File-by-File Fixes

### AdminBot.py
```python
# Remove hardcoded credentials (lines 2529-2531, 2583-2584)
# Replace: except Exception: → except (ValueError, RuntimeError, OSError):
# Replace: datetime.utcnow() → utc_now()
```

### SellerBot.py
```python
# Add path validation before file operations (line 510)
from app.utils.security_utils import validate_path
if not validate_path(file_path):
    raise ValueError("Invalid path")
```

### BuyerBot.py
```python
# Fix resource leaks (lines 2136-2137, 2220-2221)
# Use: with open(file) as f: instead of f = open(file)
```

### UpiPaymentService.py
```python
# Sanitize user input (lines 314-324, 500-518)
from app.utils.security_utils import sanitize_message
safe_text = sanitize_message(user_input)
```

### All Service Files
```python
# Replace datetime.utcnow()
from app.utils.datetime_utils import utc_now
dt = utc_now()  # Instead of datetime.utcnow()
```

## Environment Variables

Ensure `.env` has:
```
API_ID=your_id
API_HASH=your_hash
BUYER_BOT_TOKEN=your_token
SELLER_BOT_TOKEN=your_token
ADMIN_BOT_TOKEN=your_token
MONGO_URI=your_uri
SESSION_ENCRYPTION_KEY=your_key
WEBHOOK_TOKEN=your_webhook_token
ADMIN_USER_IDS=your_admin_ids
```

## Verification

After fixes:
```bash
# Scan for remaining issues
python fix_issues.py

# Check for credentials
grep -r "password\|token\|key" app/ --include="*.py" | grep -v "os.getenv"

# Check for naive datetime
grep -r "datetime.utcnow()" app/ --include="*.py"

# Check for generic exceptions
grep -r "except Exception:" app/ --include="*.py"
```

## Deployment

Only deploy after:
- ✅ All critical issues fixed
- ✅ Code review passes
- ✅ No credentials in code
- ✅ All tests pass
- ✅ Security scan clean

## Support Files

- `SECURITY_SUMMARY.md` - Full issue overview
- `SECURITY_CHECKLIST.md` - Line-by-line checklist
- `SECURITY_FIXES.md` - Implementation details
- `FIXES_TEMPLATE.py` - Code examples
- `requirements_secure.txt` - Updated dependencies
- `fix_issues.py` - Automated scanner
