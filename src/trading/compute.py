from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class ComputeConfig:
    device: str = "auto"
    precision_mode: str = "float32"
    memory_cap_mb: int = 4096
    batch_size: int = 1024

    @classmethod
    def from_file(cls, path: str | Path) -> "ComputeConfig":
        config_path = Path(path)
        if not config_path.exists():
            return cls()

        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        return cls(
            device=str(raw.get("device", "auto")),
            precision_mode=str(raw.get("precision_mode", "float32")),
            memory_cap_mb=int(raw.get("memory_cap_mb", 4096)),
            batch_size=int(raw.get("batch_size", 1024)),
        )


class ComputeBackend:
    def __init__(self, device: str = "auto") -> None:
        self.requested_device = device
        self.device = self._resolve_device(device)

    @staticmethod
    def _resolve_device(device: str) -> str:
        wanted = device.lower().strip()
        if wanted in {"cpu", "cuda", "mps"}:
            if wanted == "cuda" and not ComputeBackend._cuda_available():
                return "cpu"
            if wanted == "mps" and not ComputeBackend._mps_available():
                return "cpu"
            return wanted

        if ComputeBackend._cuda_available():
            return "cuda"
        if ComputeBackend._mps_available():
            return "mps"
        return "cpu"

    @staticmethod
    def _cuda_available() -> bool:
        try:
            import torch

            return bool(torch.cuda.is_available())
        except Exception:
            return False

    @staticmethod
    def _mps_available() -> bool:
        try:
            import torch

            return bool(getattr(torch.backends, "mps", None) and torch.backends.mps.is_available())
        except Exception:
            return False

    def telemetry(self) -> dict[str, str]:
        return {
            "requested_device": self.requested_device,
            "resolved_device": self.device,
        }
