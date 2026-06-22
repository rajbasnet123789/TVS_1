import base64
import logging

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

from app.config import settings

logger = logging.getLogger(__name__)

_cache: Fernet | None = None


def _get_fernet() -> Fernet:
    global _cache
    if _cache is None:
        salt = settings.encryption_salt.encode() if settings.encryption_salt else b"poultry_monitoring_kdf_salt"
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = kdf.derive(settings.encryption_key.encode())
        _cache = Fernet(base64.urlsafe_b64encode(key))
    return _cache


def encrypt_camera_password(plaintext: str) -> str:
    if not plaintext:
        return ""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_camera_password(ciphertext: str) -> str:
    if not ciphertext:
        return ""
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except Exception as e:
        logger.exception("Failed to decrypt camera password")
        raise e
