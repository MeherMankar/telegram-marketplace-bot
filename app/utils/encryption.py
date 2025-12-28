import os
from cryptography.fernet import Fernet
import base64
import binascii
import logging

logger = logging.getLogger(__name__)

def get_encryption_key():
    key = os.getenv('SESSION_ENCRYPTION_KEY')
    if not key:
        raise ValueError("SESSION_ENCRYPTION_KEY not set")
    
    # Ensure key is 32 bytes for Fernet
    if len(key) < 32:
        key = key.ljust(32, '0')
    elif len(key) > 32:
        key = key[:32]
    
    return base64.urlsafe_b64encode(key.encode())

def encrypt_session(data: bytes) -> bytes:
    f = Fernet(get_encryption_key())
    return f.encrypt(data)

def decrypt_session(encrypted_data: bytes) -> bytes:
    f = Fernet(get_encryption_key())
    return f.decrypt(encrypted_data)

def encrypt_data(data: str) -> str:
    """Encrypt string data and return base64 encoded string"""
    f = Fernet(get_encryption_key())
    encrypted = f.encrypt(data.encode())
    return base64.b64encode(encrypted).decode()

def decrypt_data(encrypted_data: str) -> str:
    """Decrypt base64 encoded string and return original string"""
    f = Fernet(get_encryption_key())
    try:
        encrypted_bytes = base64.b64decode(encrypted_data.encode())
    except (binascii.Error, TypeError) as e:
        # Input is not valid base64 — likely already a plaintext session string.
        logger.debug(f"decrypt_data: input not base64, returning as-is: {e}")
        return encrypted_data

    try:
        decrypted = f.decrypt(encrypted_bytes)
        return decrypted.decode()
    except Exception as e:
        # Decryption failed (bad key or data) — log and return original to allow
        # callers to fallback to using the session string directly.
        logger.warning(f"decrypt_data: decryption failed, returning original data: {e}")
        return encrypted_data