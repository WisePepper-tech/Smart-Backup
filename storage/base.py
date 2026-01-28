from abc import ABC, abstractmethod
from pathlib import Path


class BaseStorage(ABC):
    @abstractmethod
    def upload_file(self, local_path: Path, remote_path: str) -> None:
        pass

    @abstractmethod
    def download_file(self, remote_path: str, local_path: Path) -> None:
        pass

    @abstractmethod
    def list_files(self, prefix: str = "") -> list[str]:
        pass
