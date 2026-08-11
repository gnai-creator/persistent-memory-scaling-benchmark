"""Read-only TG-0 host and deployment inspection."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _command(*args: str) -> dict[str, Any]:
    executable = shutil.which(args[0])
    if not executable:
        return {"available": False, "command": list(args)}
    result = subprocess.run(args, capture_output=True, text=True, timeout=30, check=False)
    return {
        "available": True,
        "command": list(args),
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def collect_preflight(compose_path: Path, upstream_path: Path) -> dict[str, Any]:
    disk = shutil.disk_usage(compose_path.parent)
    compose_hash = sha256_file(compose_path)
    upstream_commit = _command("git", "-C", str(upstream_path), "rev-parse", "HEAD")
    return {
        "schema_version": "tg-preflight-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "cpu_count": os.cpu_count(),
        },
        "disk": {"total": disk.total, "used": disk.used, "free": disk.free},
        "docker": _command("docker", "version", "--format", "{{json .}}"),
        "compose": _command("docker", "compose", "version", "--short"),
        "gpu": _command("nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"),
        "ollama": _command("ollama", "list"),
        "deployment": {"compose_path": str(compose_path), "compose_sha256": compose_hash},
        "upstream": {"path": str(upstream_path), "commit": upstream_commit},
    }


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
