"""LLM 客户端工厂：按配置选择实现（auto/null/deepseek）。"""

from __future__ import annotations

import logging

from ..config import AppConfig
from .base import LLMClient, LLMError
from .deepseek import DeepSeekLLM
from .null import NullLLM

logger = logging.getLogger(__name__)


def build_llm(config: AppConfig) -> LLMClient:
    """构建 LLM 客户端。

    auto：有 DEEPSEEK_API_KEY 用 DeepSeek，否则降级 NullLLM（判定不受影响）。
    null：强制本地实现。deepseek：必须配置 Key，否则报错。
    """
    provider = config.llm_provider
    if provider == "null":
        return NullLLM()
    if provider == "deepseek":
        if not config.deepseek_api_key:
            raise LLMError("LLM provider=deepseek 但未配置 DEEPSEEK_API_KEY")
        return DeepSeekLLM(
            api_key=config.deepseek_api_key,
            model=config.deepseek_model,
            base_url=config.deepseek_base_url,
            timeout=config.deepseek_timeout,
            max_tokens=config.deepseek_max_tokens,
        )
    if provider == "auto":
        if config.deepseek_api_key:
            return DeepSeekLLM(
                api_key=config.deepseek_api_key,
                model=config.deepseek_model,
                base_url=config.deepseek_base_url,
                timeout=config.deepseek_timeout,
                max_tokens=config.deepseek_max_tokens,
            )
        logger.info("未配置 DEEPSEEK_API_KEY，LLM 降级为本地实现（null）")
        return NullLLM()
    raise LLMError(f"未知 LLM provider: {provider}（支持 auto/null/deepseek）")
