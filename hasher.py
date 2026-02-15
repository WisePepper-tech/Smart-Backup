import hashlib
from pathlib import Path

def get_file_hash(path: Path, block_size: int = 65536) -> str:
    sha256 = hashlib.sha256()
    try:
        with path.open("rb") as f:
            for block in iter(lambda: f.read(block_size), b""):
                sha256.update(block)
    except (PermissionError, OSError) as e:
        return None
        
    return sha256.hexdigest()