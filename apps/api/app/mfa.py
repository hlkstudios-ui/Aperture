import base64
import hashlib
import secrets

import pyotp
from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


def _fernet() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(get_settings().session_secret.encode()).digest())
    return Fernet(key)


def encrypt_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode()).decode()


def decrypt_secret(encrypted: str) -> str:
    try:
        return _fernet().decrypt(encrypted.encode()).decode()
    except InvalidToken as error:
        raise ValueError("MFA secret cannot be decrypted with the configured key") from error


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name="Aperture Studio")


def verify_totp(secret: str, code: str) -> bool:
    return pyotp.TOTP(secret).verify(code, valid_window=1)


def generate_recovery_codes(count: int = 8) -> list[str]:
    return [f"{secrets.token_hex(4)}-{secrets.token_hex(4)}" for _ in range(count)]


def hash_recovery_code(code: str) -> str:
    return hashlib.sha256(code.strip().lower().encode()).hexdigest()
