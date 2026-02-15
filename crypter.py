import os
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes


class FileCrypter:
    def __init__(self, password: str, salt: bytes = None):
        # If there is no salt, we create it (for backup), if there is, we use it (for recovery)
        self.salt = salt or os.urandom(16)

        # PBKDF2 turns a password into a secure 32-byte key
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=self.salt,
            iterations=100000,
        )
        self.key = kdf.derive(password.encode())
        self.aead = ChaCha20Poly1305(self.key)

    def encrypt(self, data: bytes) -> bytes:
        nonce = os.urandom(12)
        # We encrypt the data. Poly1305 will add a verification tag automatically
        ciphertext = self.aead.encrypt(nonce, data, None)
        return nonce + ciphertext

    def decrypt(self, encrypted_data: bytes) -> bytes:
        nonce = encrypted_data[:12]
        ciphertext = encrypted_data[12:]
        # If the password is incorrect or the file has been changed, an exception will be thrown here.
        return self.aead.decrypt(nonce, ciphertext, None)
