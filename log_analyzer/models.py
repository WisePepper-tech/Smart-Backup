from enum import Enum
from dataclasses import dataclass
from nginx_parser import LogRecord


class ThreatReason(Enum):
    THRESHOLD_EXCEEDED = "threshold_exceeded"
    KNOWN_SCANNER = "known_scanner"


class Severity(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class ThreatEvent:
    record: LogRecord
    reason: ThreatReason
    severity: Severity
