"""应用配置：环境变量 + 默认值。

环境变量解析失败（如 DEEPSEEK_TIMEOUT=abc）时回退默认值并告警，
不阻断启动；LLM 相关配置只影响辅助层，判定始终可用。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_KB_DIR = Path(__file__).resolve().parents[2] / "knowledge_base"


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except ValueError:
        logger.warning("%s=%r 不是合法数值，回退默认 %s", name, os.environ.get(name), default)
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        logger.warning("%s=%r 不是合法整数，回退默认 %s", name, os.environ.get(name), default)
        return default


@dataclass(frozen=True)
class AppConfig:
    kb_dir: Path = field(default_factory=lambda: Path(_env("COMPLIANCE_KB_DIR", str(DEFAULT_KB_DIR))))
    llm_provider: str = field(default_factory=lambda: _env("COMPLIANCE_LLM_PROVIDER", "auto"))
    deepseek_api_key: str = field(default_factory=lambda: _env("DEEPSEEK_API_KEY", ""))
    deepseek_base_url: str = field(default_factory=lambda: _env("DEEPSEEK_BASE_URL", "https://api.deepseek.com"))
    deepseek_model: str = field(default_factory=lambda: _env("DEEPSEEK_MODEL", "deepseek-flash"))
    deepseek_timeout: float = field(default_factory=lambda: _env_float("DEEPSEEK_TIMEOUT", 30.0))
    deepseek_max_tokens: int = field(default_factory=lambda: _env_int("DEEPSEEK_MAX_TOKENS", 2048))
    llm_max_clauses: int = 6

    @property
    def policies_dir(self) -> Path:
        return self.kb_dir / "policies"

    @property
    def clauses_dir(self) -> Path:
        return self.kb_dir / "clauses"
