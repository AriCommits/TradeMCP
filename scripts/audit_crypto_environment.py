"""Write a secret-safe local capability audit for crypto movement research."""

from __future__ import annotations

import argparse
import ctypes
import importlib.metadata
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PACKAGE_NAMES = (
    "numpy",
    "pandas",
    "scikit-learn",
    "scipy",
    "pyarrow",
    "duckdb",
    "PyYAML",
    "torch",
    "lightgbm",
    "optuna",
    "statsmodels",
)


def _package_versions(names: Sequence[str] = PACKAGE_NAMES) -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for name in names:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def _memory_bytes() -> int | None:
    if os.name == "nt":
        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong),
                ("memory_load", ctypes.c_ulong),
                ("total_physical", ctypes.c_ulonglong),
                ("available_physical", ctypes.c_ulonglong),
                ("total_page_file", ctypes.c_ulonglong),
                ("available_page_file", ctypes.c_ulonglong),
                ("total_virtual", ctypes.c_ulonglong),
                ("available_virtual", ctypes.c_ulonglong),
                ("available_extended_virtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.length = ctypes.sizeof(MemoryStatus)
        try:
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.total_physical)
        except (AttributeError, OSError):
            return None
        return None
    sysconf = getattr(os, "sysconf", None)
    if sysconf is None:
        return None
    try:
        page_size = sysconf("SC_PAGE_SIZE")
        page_count = sysconf("SC_PHYS_PAGES")
    except (AttributeError, OSError, ValueError):
        return None
    return int(page_size * page_count)


def _gpu_inventory() -> dict[str, Any]:
    command = [
        "nvidia-smi",
        "--query-gpu=name,memory.total,driver_version",
        "--format=csv,noheader,nounits",
    ]
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return {"status": "unavailable", "devices": []}
    if result.returncode != 0:
        return {"status": "unavailable", "devices": []}
    devices = []
    for raw_line in result.stdout.splitlines():
        parts = [part.strip() for part in raw_line.split(",")]
        if len(parts) != 3:
            continue
        try:
            memory_mib = int(parts[1])
        except ValueError:
            memory_mib = None
        devices.append(
            {
                "name": parts[0],
                "memory_mib": memory_mib,
                "driver_version": parts[2],
            }
        )
    return {"status": "available" if devices else "unavailable", "devices": devices}

def _cuda_inventory(gpu: dict[str, Any], torch_version: str | None) -> dict[str, Any]:
    runtime_version = None
    if gpu["status"] == "available":
        try:
            result = subprocess.run(
                ["nvidia-smi"],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            result = None
        if result is not None and result.returncode == 0:
            match = re.search(r"CUDA(?: UMD)? Version:\s*([0-9.]+)", result.stdout)
            runtime_version = match.group(1) if match else None
    return {
        "nvidia_driver_visible": gpu["status"] == "available",
        "reported_runtime_version": runtime_version,
        "torch_version": torch_version,
        "framework_support_verified": False,
    }


def audit_environment(root: Path) -> dict[str, Any]:
    """Return an allowlisted capability report without reading environment variables."""

    resolved = root.resolve()
    disk = shutil.disk_usage(resolved)
    gpu = _gpu_inventory()
    packages = _package_versions()
    cuda = _cuda_inventory(gpu, packages["torch"])
    return {
        "schema_version": 1,
        "audited_at_utc": datetime.now(timezone.utc).isoformat(),
        "project_root": str(resolved),
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "executable_name": Path(sys.executable).name,
        },
        "cpu": {
            "logical_count": os.cpu_count(),
            "machine": platform.machine(),
            "platform": platform.system(),
        },
        "memory": {"total_bytes": _memory_bytes()},
        "disk": {
            "total_bytes": disk.total,
            "free_bytes": disk.free,
        },
        "gpu": gpu,
        "cuda": cuda,
        "packages": packages,
        "full_download_authorized": False,
        "notes": [
            "Package presence is informational and does not authorize data collection.",
            "Venue and prop-account decisions remain governed by ProjectConfig.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/crypto_movement/environment_audit.json"),
    )
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    report = audit_environment(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
