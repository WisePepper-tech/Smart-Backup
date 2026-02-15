import sys
from classes import ProgressEvent


def show_progress(event: ProgressEvent):
    if event.total is None:
        msg = f"\r[SCANNING] Files found: {event.processed} | Current: {event.current_file[:30]}..."
    else:
        scale_width = 30
        percent = (event.processed / event.total) * 100
        filled = int(scale_width * event.processed / event.total)
        bar = "#" * filled + "-" * (scale_width - filled)
        msg = f"\r[COPYING] |{bar}| {percent:.1f}% ({event.processed}/{event.total})"

    sys.stdout.write(msg)
    sys.stdout.flush()

    if event.total and event.processed >= event.total:
        sys.stdout.write("\nDone!\n")
        sys.stdout.flush()
