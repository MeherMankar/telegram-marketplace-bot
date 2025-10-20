import os
from cryptography.fernet import Fernet
import base64

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
    encrypted_bytes = base64.b64decode(encrypted_data.encode())
    decrypted = f.decrypt(encrypted_bytes)
    return decrypted.decode()