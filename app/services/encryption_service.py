import base64
import hashlib

from cryptography.fernet import Fernet

from app.core.config import settings


class EncryptionService:
    def __init__(self):
        key_hash = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
        key = base64.urlsafe_b64encode(key_hash)
        self.cipher = Fernet(key)

    def encrypt(self, data: str) -> str:
        return self.cipher.encrypt(data.encode()).decode()

    def decrypt(self, encrypted_data: str) -> str:
        return self.cipher.decrypt(encrypted_data.encode()).decode()


encryption_service = EncryptionService()
