import os
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from argon2.low_level import hash_secret_raw, Type


class FileCrypter:
    _TIME_COST = 3
    _MEMORY_COST = 65536
    _PARALLELISM = 4
    _HASH_LEN = 32
    _SALT_LEN = 16

    def __init__(
        self,
        password: str,
        salt: bytes = None,
        time_cost: int = None,
        memory_cost: int = None,
        parallelism: int = None,
    ):
        self.salt = salt or os.urandom(self._SALT_LEN)
        self.key = hash_secret_raw(
            secret=password.encode("utf-8"),
            salt=self.salt,
            time_cost=time_cost or self._TIME_COST,
            memory_cost=memory_cost or self._MEMORY_COST,
            parallelism=parallelism or self._PARALLELISM,
            hash_len=self._HASH_LEN,
            type=Type.ID,
        )
        self.aead = ChaCha20Poly1305(self.key)

    def encrypt(self, data: bytes) -> bytes:
        nonce = os.urandom(12)
        ciphertext = self.aead.encrypt(nonce, data, None)
        return nonce + ciphertext

    def decrypt(self, encrypted_data: bytes) -> bytes:
        nonce = encrypted_data[:12]
        ciphertext = encrypted_data[12:]
        return self.aead.decrypt(nonce, ciphertext, None)
