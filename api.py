import os
import re
import json
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException, status, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, field_validator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from manager import BackupManager
from scanner import scan_files

app = FastAPI(title="Smart-Backup API")

BACKUP_BASE = Path(os.getenv("BACKUP_PATH", "./backups")).resolve()

API_KEY = os.getenv("API_KEY")
if not API_KEY:
    raise RuntimeError("API_KEY environment variable is not set")

api_key_header = APIKeyHeader(name="X-API-Key")

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

_PROJECT_NAME_RE = re.compile(r"^[a-zA-Z0-9_\-]{1,64}$")
ALLOWED_SOURCE_BASE = Path(os.getenv("ALLOWED_SOURCE_PATH", "/data")).resolve()


def verify_api_key(key: str = Security(api_key_header)) -> None:
    if key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )


class BackupRequest(BaseModel):
    source_path: str
    project_name: str
    comment: str = ""
    compress: bool = True

    @field_validator("source_path")
    @classmethod
    def validate_source_path(cls, v: str) -> str:
        try:
            path = Path(v).resolve()
        except Exception:
            raise ValueError("Invalid path")
        # Whitelist
        if not str(path).startswith(str(ALLOWED_SOURCE_BASE)):
            raise ValueError(f"source_path must be inside {ALLOWED_SOURCE_BASE}")
        return str(path)

    @field_validator("project_name")
    @classmethod
    def validate_project_name(cls, v: str) -> str:
        if not _PROJECT_NAME_RE.match(v):
            raise ValueError("project_name must be 1-64 chars: letters, digits, - or _")
        return v

    @field_validator("comment")
    @classmethod
    def validate_comment(cls, v: str) -> str:
        # We limit the length and remove the control characters
        v = v.strip()
        if len(v) > 500:
            raise ValueError("comment must be 500 chars or less")
        return v


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get(
    "/backups",
    responses={
        400: {"description": "Invalid project name"},
        403: {"description": "Invalid API key"},
        429: {"description": "Rate limit exceeded"},
    },
)
@limiter.limit("30/minute")
def list_backups(
    request: Request,
    project: str = None,
    _=Security(verify_api_key),
):
    if project is not None and not _PROJECT_NAME_RE.match(project):
        raise HTTPException(status_code=400, detail="Invalid project name")

    manager = BackupManager(BACKUP_BASE)
    versions = manager._find_target_versions(project)
    result = []
    for v in versions:
        try:
            with open(v / "manifest.json", "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            continue  # A corrupted manifest does not drop the entire list.
        result.append(
            {
                "project": v.parent.name,
                "version": v.name,
                "total_files": manifest["info"]["total_files"],
                "comment": manifest["info"].get("comment", ""),
                "encrypted": manifest["info"].get("salt") is not None,
                "compression": manifest["info"].get("compression_enabled", False),
            }
        )
    return result


@app.post(
    "/backups",
    responses={
        400: {"description": "Source path not found or not a directory"},
        403: {"description": "Invalid API key"},
        500: {"description": "Internal backup error"},
    },
)
@limiter.limit("10/minute")
def create_backup(
    request: Request,
    req: BackupRequest,
    _=Security(verify_api_key),
):
    source = Path(req.source_path)  # NOSONAR(python:S2083)
    if not source.exists():
        raise HTTPException(
            status_code=400,
            detail=f"Source path not found: {req.source_path}",
        )
    if not source.is_dir():
        raise HTTPException(
            status_code=400,
            detail="source_path must be a directory",
        )

    manager = BackupManager(BACKUP_BASE)
    try:
        scan_result = scan_files(source)
        result = manager.create_backup(
            scan_result,
            source,
            req.project_name,
            comment=req.comment,
            compress=req.compress,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "status": "ok",
        "project": req.project_name,
        "copied": result.copied,
        "skipped": result.skipped,
        "errors": result.errors,
    }
