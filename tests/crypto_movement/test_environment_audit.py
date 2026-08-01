from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/audit_crypto_environment.py"


def _module():
    spec = importlib.util.spec_from_file_location("audit_crypto_environment", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_audit_has_allowlisted_capabilities_and_no_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("TEST_API_SECRET", "never-serialize-this")
    module = _module()
    report = module.audit_environment(tmp_path)
    assert report["schema_version"] == 1
    for key in ("cpu", "memory", "disk", "python", "gpu", "cuda", "packages"):
        assert key in report
    serialized = json.dumps(report)
    assert "TEST_API_SECRET" not in serialized
    assert "never-serialize-this" not in serialized
    assert set(report["packages"]) == set(module.PACKAGE_NAMES)


def test_missing_nvidia_smi_is_nonfatal(monkeypatch):
    module = _module()

    def missing(*args, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(module.subprocess, "run", missing)
    assert module._gpu_inventory() == {"status": "unavailable", "devices": []}


def test_cli_writes_json(tmp_path):
    output = tmp_path / "audit.json"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--root",
            str(tmp_path),
            "--output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["schema_version"] == 1
    assert report["project_root"] == str(tmp_path.resolve())
