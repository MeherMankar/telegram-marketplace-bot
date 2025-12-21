# Security Checklist

## Critical Fixes Required

### 1. Path Traversal (CWE-22) - HIGH PRIORITY
- [ ] Import `validate_path` from `app.utils.security_utils`
- [ ] Validate all file paths before use
- [ ] Use `get_safe_filename()` for user-provided filenames
- [ ] Files to fix:
  - UniversalSessionConverter.py (lines 64, 76, 92, 93, 148, 149, 192, 193, 221, 248, 369, 408)
  - TDataConverter.py (lines 17, 27, 105, 120, 141)
  - SellerBot.py (line 510)
  - OtpService.py (line 116)
  - AccountLoginService.py (line 162)
  - AccountTransferService.py (lines 212, 218)
  - BackupService.py (lines 185, 190, 205, 212)
  - ComplianceService.py (lines 68, 409)
  - SimpleOtpService.py (line 127)

### 2. Hardcoded Credentials (CWE-798) - CRITICAL
- [ ] Remove all hardcoded credentials from code
- [ ] Use environment variables only
- [ ] Files to fix:
  - AdminBot.py (lines 2529-2531, 2583-2584)
  - VerificationService.py (line 354)

### 3. Generic Exception Handling (CWE-396/397) - HIGH
- [ ] Replace `except Exception:` with specific exceptions
- [ ] Add proper error logging
- [ ] Files to fix:
  - AdminBot.py (lines 276, 283, 407, 460, 555, 611)
  - SellerBot.py (line 212)
  - BuyerBot.py (lines 214, 221, 279)
  - UniversalSessionConverter.py (line 76)
  - TDataConverter.py (line 129)
  - OtpService.py (lines 145, 167)
  - BaseBot.py (line 64)
  - SimpleOtpService.py (line 170)

### 4. Naive Datetime Objects - MEDIUM
- [ ] Replace all `datetime.utcnow()` with `utc_now()`
- [ ] Import from `app.utils.datetime_utils`
- [ ] Affects 100+ lines across all service files

### 5. Resource Leaks (CWE-400/664) - MEDIUM
- [ ] Use context managers for all file operations
- [ ] Ensure proper cleanup in try/finally blocks
- [ ] Files to fix:
  - UniversalSessionConverter.py (lines 92-94, 148-150, 192-194)
  - BuyerBot.py (lines 2136-2137, 2220-2221)
  - SessionImporter.py (lines 51-52)

### 6. Cross-Site Scripting (CWE-79/80) - HIGH
- [ ] Sanitize all user input in messages
- [ ] Use `sanitize_message()` from `app.utils.security_utils`
- [ ] Files to fix:
  - UpiPaymentService.py (lines 314-324, 500-518)
  - PaymentService.py (lines 232-241)
  - BackupService.py (line 190)

### 7. Sensitive Information Leak (CWE-200) - HIGH
- [ ] Never log session strings, auth keys, passwords
- [ ] Remove debug prints with sensitive data
- [ ] Files to fix:
  - SocialService.py (lines 25-31)
  - AccountTransferService.py (lines 78-90)

### 8. CSRF Protection (CWE-352) - MEDIUM
- [ ] Add webhook token validation
- [ ] Verify request origin
- [ ] Files to fix:
  - main.py (lines 145-147)

## Implementation Order

1. **Phase 1 (Critical)**: Fix hardcoded credentials and path traversal
2. **Phase 2 (High)**: Fix exception handling and XSS vulnerabilities
3. **Phase 3 (Medium)**: Fix datetime, resource leaks, CSRF
4. **Phase 4 (Low)**: Code quality improvements

## Testing After Fixes

```bash
# Run security scan
python fix_issues.py

# Run code review
# Use Code Issues Panel to verify fixes

# Test functionality
pytest tests/

# Check for credentials in code
grep -r "password\|token\|key" app/ --include="*.py" | grep -v "os.getenv"
```

## Deployment Checklist

- [ ] All credentials in environment variables
- [ ] No hardcoded values in code
- [ ] All exceptions properly handled
- [ ] No sensitive data in logs
- [ ] Path validation on all file operations
- [ ] CSRF tokens validated
- [ ] Dependencies updated to secure versions
- [ ] Code review passed
- [ ] Security tests passed
