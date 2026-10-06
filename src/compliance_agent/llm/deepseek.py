"""DeepSeek 适配器：OpenAI 兼容接口，仅做检索排序/归纳/缺失提示。

官方文档要点（2026-10 确认）：
- base_url=https://api.deepseek.com，环境变量 DEEPSEEK_API_KEY
- 支持 response_format={"type": "json_object"}，prompt 中需出现 "json" 并给出目标结构
- JSON 模式可能偶发空响应 → 按 LLMError 处理，由上层降级
"""

from __future__ import annotations

import json
import time
from typing import Any

from openai import AuthenticationError, OpenAI

from ..knowledge.clauses import Clause
from ..models import ClauseSummary, SubscriptionApplication
from .base import LLMError

SYSTEM_PROMPT = (
    "你是跨境数据合规评估的辅助模型，职责仅限于：1) 对候选条款做相关性排序；"
    "2) 归纳条款内容要点；3) 提示申请中可能缺失的信息。"
    "你没有判定权限：禁止输出 allow/deny/manual_review 判定或任何放行建议，"
    "最终判定由确定性策略引擎独立完成。请始终输出合法 JSON。"
)

MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 0.5


def parse_json_content(content: str | None) -> dict:
    """解析模型返回的 JSON：剥代码围栏、容错空白；失败抛 LLMError。"""
    if not content or not content.strip():
        raise LLMError("模型返回空内容")
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("\n") + 1 :] if "\n" in text else ""
        text = text.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMError(f"模型返回非 JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise LLMError(f"模型返回 JSON 顶层不是对象: {type(data).__name__}")
    return data


class DeepSeekLLM:
    """OpenAI SDK 客户端（base_url 指向 DeepSeek）。"""

    name = "deepseek"

    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-flash",
        base_url: str = "https://api.deepseek.com",
        timeout: float = 30.0,
        max_tokens: int = 2048,
    ) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)

    def _chat_json(self, user_prompt: str) -> dict:
        """带重试的 JSON 调用；鉴权错误不重试，其余错误重试后抛 LLMError。"""
        last_error: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = self._client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    response_format={"type": "json_object"},
                    max_tokens=self.max_tokens,
                    temperature=0,
                )
                content = response.choices[0].message.content
                return parse_json_content(content)
            except AuthenticationError as exc:
                raise LLMError(f"DeepSeek 鉴权失败，请检查 DEEPSEEK_API_KEY: {exc}") from exc
            except LLMError as exc:
                last_error = exc
            except Exception as exc:  # 网络/服务端错误（OpenAI SDK 异常体系）
                last_error = exc
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)
        raise LLMError(f"DeepSeek 调用失败（重试 {MAX_RETRIES} 次）: {last_error}") from last_error

    @staticmethod
    def _app_text(app: SubscriptionApplication) -> str:
        return (
            f"申请 ID: {app.application_id}；申请方: {app.applicant.organization_id}（{app.applicant.region}）；"
            f"用途: {app.purpose}（{app.purpose_description or '无描述'}）；"
            f"数据类型: {', '.join(app.data_types)}；字段: {', '.join(app.data_fields)}；"
            f"接收方: {app.recipient}；保存期限: {app.retention_days} 天"
        )

    def rank_clauses(self, app: SubscriptionApplication, clauses: list[Clause]) -> list[str]:
        clause_list = "\n".join(
            f"- {c.clause_id}: {c.title}（关键词: {', '.join(c.keywords)}）" for c in clauses
        )
        prompt = (
            f"根据申请内容对候选条款做相关性排序，输出 json: "
            f'{{"relevant": ["clause_id 按相关性降序..."]}}\n\n'
            f"申请内容：\n{self._app_text(app)}\n\n候选条款：\n{clause_list}"
        )
        data = self._chat_json(prompt)
        raw = data.get("relevant")
        if not isinstance(raw, list):
            raise LLMError("rank_clauses 返回格式错误：缺少 relevant 列表")
        known = {c.clause_id for c in clauses}
        return [cid for cid in raw if isinstance(cid, str) and cid in known]

    def summarize_clauses(self, app: SubscriptionApplication, clauses: list[Clause]) -> list[ClauseSummary]:
        clause_list = "\n\n".join(
            f"条款 {c.clause_id}（{c.title}）：\n{c.body[:2000]}" for c in clauses
        )
        prompt = (
            f"对以下条款做一句话归纳（面向理赔审批人员），输出 json: "
            f'{{"summaries": [{{"clause_id": "...", "summary": "..."}}]}}\n\n'
            f"申请内容：\n{self._app_text(app)}\n\n条款内容：\n{clause_list}"
        )
        data = self._chat_json(prompt)
        raw = data.get("summaries")
        if not isinstance(raw, list):
            raise LLMError("summarize_clauses 返回格式错误：缺少 summaries 列表")
        known = {c.clause_id for c in clauses}
        summaries: list[ClauseSummary] = []
        for item in raw:
            clause_id = item.get("clause_id") if isinstance(item, dict) else None
            if not isinstance(clause_id, str) or clause_id not in known:
                continue
            text = item.get("summary")
            if isinstance(text, str) and text.strip():
                summaries.append(ClauseSummary(clause_id=clause_id, summary=text.strip()))
        return summaries

    def suggest_missing_info(self, app: SubscriptionApplication) -> list[str]:
        prompt = (
            f"结合申请内容，提示可能缺失的合规信息（如证据材料、字段说明），"
            f"仅提示、不做判定，输出 json: {{\"hints\": [\"...\"]}}\n\n申请内容：\n{self._app_text(app)}"
        )
        data = self._chat_json(prompt)
        raw = data.get("hints")
        if not isinstance(raw, list):
            raise LLMError("suggest_missing_info 返回格式错误：缺少 hints 列表")
        return [h for h in raw if isinstance(h, str) and h.strip()]
