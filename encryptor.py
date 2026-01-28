from cryptography.fernet import Fernet
from pathlib import Path


def encrypt_file(path: Path, key: bytes) -> None:
    data = path.read_bytes()
    encrypted = Fernet(key).encrypt(data)
    path.write_bytes(encrypted)


def decrypt_file(path: Path, key: bytes) -> None:
    fernet = Fernet(key)

    data = path.read_bytes()
    decrypted = fernet.decrypt(data)

    path.write_bytes(decrypted)
