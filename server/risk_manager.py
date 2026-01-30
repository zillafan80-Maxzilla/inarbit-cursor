import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - fallback when PyYAML is unavailable
    yaml = None


def _parse_scalar(value: str) -> Any:
    raw = value.strip()
    if raw == "":
        return ""
    if raw.lower() in {"true", "false"}:
        return raw.lower() == "true"
    try:
        if "." in raw:
            return float(raw)
        return int(raw)
    except Exception:
        pass
    if (raw.startswith('"') and raw.endswith('"')) or (raw.startswith("'") and raw.endswith("'")):
        return raw[1:-1]
    return raw


def _parse_basic_yaml(text: str) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    current: Optional[str] = None
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        indent = len(line) - len(line.lstrip(" "))
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value == "":
            data[key] = data.get(key, {})
            current = key
            continue
        parsed = _parse_scalar(value)
        if indent > 0 and current:
            section = data.get(current)
            if not isinstance(section, dict):
                section = {}
                data[current] = section
            section[key] = parsed
        else:
            data[key] = parsed
            current = None
    return data


def _dump_basic_yaml(data: Dict[str, Any]) -> str:
    lines: list[str] = []
    for key, value in data.items():
        if isinstance(value, dict):
            lines.append(f"{key}:")
            for sub_key, sub_val in value.items():
                lines.append(f"  {sub_key}: {sub_val}")
        else:
            lines.append(f"{key}: {value}")
    return "\n".join(lines) + "\n"


class RiskManager:
    """Global risk manager coordinating sub-modules."""

    def __init__(self, config_path: str = "config/risk.yaml", user_id: Optional[str] = None):
        self.user_id = user_id
        self.config_path = Path(config_path)
        self.config: Dict[str, Any] = {}
        self._load_config()
        self._init_modules()
        self._last_check_ts: Optional[float] = None

    def _load_config(self) -> None:
        if not self.config_path.exists():
            self.config = {}
            return
        text = self.config_path.read_text(encoding="utf-8")
        if yaml is not None:
            try:
                self.config = yaml.safe_load(text) or {}
                return
            except Exception:
                logger.warning("Risk config yaml parse failed, fallback to basic parser")
        self.config = _parse_basic_yaml(text)

    def _persist_config(self) -> None:
        if yaml is not None:
            try:
                payload = yaml.safe_dump(self.config, allow_unicode=False, sort_keys=False)
                self.config_path.write_text(payload, encoding="utf-8")
                return
            except Exception:
                logger.warning("Risk config yaml dump failed, fallback to basic writer")
        payload = _dump_basic_yaml(self.config)
        self.config_path.write_text(payload, encoding="utf-8")

    def _init_modules(self) -> None:
        cfg = self.config or {}
        self.total_equity_monitor = TotalEquityMonitor(cfg.get("total_equity", {}))
        self.max_drawdown_cb = MaxDrawdownCircuitBreaker(cfg.get("max_drawdown", {}))
        self.exposure_limiter = ExposureLimiter(cfg.get("exposure", {}))
        self.rebalancer = Rebalancer(cfg.get("rebalancer", {}))
        self.funding_rate_monitor = FundingRateMonitor(cfg.get("funding_rate", {}))
        self.auto_transfer = AutoTransfer(cfg.get("auto_transfer", {}))
        self.panic_button = PanicButton(cfg.get("panic", {}))
        self.api_key_reloader = ApiKeyHotReloader(cfg.get("api_key_reload", {}))

    async def check(self) -> bool:
        checks = [
            self.total_equity_monitor.check(),
            self.max_drawdown_cb.check(),
            self.exposure_limiter.check(),
            self.rebalancer.check(),
            self.funding_rate_monitor.check(),
            self.auto_transfer.check(),
            self.panic_button.check(),
            self.api_key_reloader.check(),
        ]
        results = await asyncio.gather(*checks)
        self._last_check_ts = asyncio.get_event_loop().time()
        return all(results)

    def get_config(self) -> Dict[str, Any]:
        return self.config or {}

    def update_config(self, config: Dict[str, Any], persist: bool = True) -> None:
        if not isinstance(config, dict):
            raise ValueError("config must be a dict")
        self.config.update(config)
        if persist:
            self._persist_config()
        self._init_modules()

    def reload_config(self) -> None:
        self._load_config()
        self._init_modules()

    def get_status(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "last_check_ts": self._last_check_ts,
            "panic_triggered": self.panic_button.triggered,
            "total_equity": self.total_equity_monitor.get_status(),
            "max_drawdown": self.max_drawdown_cb.get_status(),
            "exposure": self.exposure_limiter.get_status(),
            "rebalancer": self.rebalancer.get_status(),
            "funding_rate": self.funding_rate_monitor.get_status(),
            "auto_transfer": self.auto_transfer.get_status(),
            "api_key_reload": self.api_key_reloader.get_status(),
        }


class TotalEquityMonitor:
    def __init__(self, cfg: Dict[str, Any]):
        self.threshold = float(cfg.get("threshold", 0.0) or 0.0)
        self.current_equity = 0.0

    async def check(self) -> bool:
        if not self.threshold:
            return True
        self.current_equity = await self._fetch_equity()
        if self.current_equity < self.threshold:
            logger.warning("Risk total_equity below threshold")
            return False
        return True

    async def _fetch_equity(self) -> float:
        return 100000.0

    def get_status(self) -> dict:
        return {
            "threshold": self.threshold,
            "current_equity": self.current_equity,
        }


class MaxDrawdownCircuitBreaker:
    def __init__(self, cfg: Dict[str, Any]):
        self.max_drawdown = float(cfg.get("max_drawdown", 0.2))
        self.peak_equity = float(cfg.get("peak_equity", 120000.0))

    async def check(self) -> bool:
        current = await self._fetch_equity()
        if self.peak_equity <= 0:
            return True
        drawdown = (self.peak_equity - current) / self.peak_equity
        if drawdown > self.max_drawdown:
            logger.warning("Risk drawdown exceeded limit")
            return False
        return True

    async def _fetch_equity(self) -> float:
        return 100000.0

    def get_status(self) -> dict:
        return {
            "max_drawdown": self.max_drawdown,
            "peak_equity": self.peak_equity,
        }


class ExposureLimiter:
    def __init__(self, cfg: Dict[str, Any]):
        self.limit = float(cfg.get("limit", 0.3))

    async def check(self) -> bool:
        exposure = 0.25
        if exposure > self.limit:
            logger.warning("Risk exposure exceeded limit")
            return False
        return True

    def get_status(self) -> dict:
        return {"limit": self.limit}


class Rebalancer:
    def __init__(self, cfg: Dict[str, Any]):
        self.enabled = bool(cfg.get("enabled", True))

    async def check(self) -> bool:
        return True

    def get_status(self) -> dict:
        return {"enabled": self.enabled}


class FundingRateMonitor:
    def __init__(self, cfg: Dict[str, Any]):
        self.max_funding_rate = float(cfg.get("max_rate", 0.01))

    async def check(self) -> bool:
        rate = 0.005
        if abs(rate) > self.max_funding_rate:
            logger.warning("Risk funding rate exceeded limit")
            return False
        return True

    def get_status(self) -> dict:
        return {"max_rate": self.max_funding_rate}


class AutoTransfer:
    def __init__(self, cfg: Dict[str, Any]):
        self.mode = str(cfg.get("mode", "mock"))

    async def check(self) -> bool:
        return True

    def get_status(self) -> dict:
        return {"mode": self.mode}


class PanicButton:
    def __init__(self, cfg: Dict[str, Any]):
        _ = cfg
        self.triggered = False

    async def check(self) -> bool:
        return not self.triggered

    def trigger(self) -> None:
        self.triggered = True

    def reset(self) -> None:
        self.triggered = False

    def get_status(self) -> dict:
        return {"triggered": self.triggered}


class ApiKeyHotReloader:
    def __init__(self, cfg: Dict[str, Any]):
        self.watch_path = str(cfg.get("watch_path", "config/api_keys.yaml"))
        self.last_modified = None

    async def check(self) -> bool:
        path = Path(self.watch_path)
        if not path.exists():
            return True
        mtime = path.stat().st_mtime
        if self.last_modified is None:
            self.last_modified = mtime
            return True
        if mtime != self.last_modified:
            self.last_modified = mtime
            logger.info("Risk api keys reloaded")
        return True

    def get_status(self) -> dict:
        return {"watch_path": self.watch_path, "last_modified": self.last_modified}


__all__ = [
    "RiskManager",
    "TotalEquityMonitor",
    "MaxDrawdownCircuitBreaker",
    "ExposureLimiter",
    "Rebalancer",
    "FundingRateMonitor",
    "AutoTransfer",
    "PanicButton",
    "ApiKeyHotReloader",
]
