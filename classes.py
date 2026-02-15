from dataclasses import dataclass, field
from typing import List, Optional
from pathlib import Path


@dataclass
class ScanResult:
    files: List[Path]
    total_size: int
    total_files: int
    file_hashes: dict[Path, str] = field(default_factory=dict)


@dataclass
class CopyResult:
    copied: int
    skipped: int
    quantity_versions: int
    errors: int


@dataclass
class ProgressEvent:
    processed: int
    total: Optional[int] = None
    current_file: str = ""
