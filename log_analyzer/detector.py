from nginx_parser import LogRecord
from .models import ThreatEvent, ThreatReason, Severity


def requests_per_minute(record: LogRecord) -> float:
    if len(record.timestamps) < 2:
        return 0.0
    duration = (record.timestamps[-1] - record.timestamps[0]).total_seconds()
    if duration == 0:
        return 0.0
    return len(record.timestamps) / (duration / 60)
