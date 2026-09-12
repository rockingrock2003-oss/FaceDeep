from cryptography.fernet import Fernet

from app.core.config import settings


class EncryptionService:
    def __init__(self):
        key = settings.SECRET_KEY.encode()
        if len(key) < 32:
            key = key.ljust(32, b"=")
        self.cipher = Fernet(key[:32])

    def encrypt(self, data: str) -> str:
        return self.cipher.encrypt(data.encode()).decode()

    def decrypt(self, encrypted_data: str) -> str:
        return self.cipher.decrypt(encrypted_data.encode()).decode()


encryption_service = EncryptionService()
