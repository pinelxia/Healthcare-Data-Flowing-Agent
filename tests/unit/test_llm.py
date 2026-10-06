"""LLM 层测试：NullLLM、DeepSeek 解析/重试、工厂选择。"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from openai import AuthenticationError

from compliance_agent.llm.base import LLMError
from compliance_agent.llm.deepseek import DeepSeekLLM, parse_json_content
from compliance_agent.llm.factory import build_llm
from compliance_agent.llm.null import NullLLM
from compliance_agent.config import AppConfig
from compliance_agent.knowledge.clauses import Clause
from tests.conftest import make_application

APP = make_application()
CLAUSES = [
    Clause(
        clause_id="CLS-1",
        title="条款一",
        keywords=["理赔"],
        summary="模板摘要一",
        body="正文第一行\n更多内容",
        file="a.md",
    ),
    Clause(clause_id="CLS-2", title="条款二", keywords=[], summary="", body="正文第二行", file="b.md"),
]


# ---------- NullLLM ----------


def test_null_llm_ranks_by_local_score():
    null = NullLLM()
    ranked = null.rank_clauses(APP, CLAUSES)

    assert ranked[0] == "CLS-1"


def test_null_llm_summarizes_from_frontmatter_or_body_first_line():
    null = NullLLM()
    summaries = null.summarize_clauses(APP, CLAUSES)

    assert {s.clause_id: s.summary for s in summaries} == {
        "CLS-1": "模板摘要一",
        "CLS-2": "正文第二行",
    }


def test_null_llm_suggests_no_hints():
    assert NullLLM().suggest_missing_info(APP) == []


# ---------- JSON 解析 ----------


def test_parse_json_content_plain():
    assert parse_json_content('{"a": 1}') == {"a": 1}


def test_parse_json_content_strips_code_fence():
    assert parse_json_content('```json\n{"a": 1}\n```') == {"a": 1}


@pytest.mark.parametrize("content", [None, "", "   ", "不是 JSON", "[1, 2]"])
def test_parse_json_content_raises_on_bad_content(content):
    with pytest.raises(LLMError):
        parse_json_content(content)


# ---------- DeepSeek 适配器（mock 客户端） ----------


def fake_client(response_content=None, error=None, call_count_cb=None):
    class FakeCompletions:
        def create(self, **kwargs):
            if call_count_cb:
                call_count_cb()
            if error:
                raise error
            msg = SimpleNamespace(content=response_content)
            choice = SimpleNamespace(message=msg)
            return SimpleNamespace(choices=[choice])

    class FakeChat:
        def __init__(self):
            self.completions = FakeCompletions()

    class FakeClient:
        def __init__(self):
            self.chat = FakeChat()

    return FakeClient()


def make_deepseek(client) -> DeepSeekLLM:
    llm = DeepSeekLLM(api_key="test-key")
    llm._client = client  # type: ignore[assignment]
    return llm


def test_rank_clauses_parses_and_filters():
    client = fake_client(response_content=json.dumps({"relevant": ["CLS-1", "UNKNOWN", 42]}))
    llm = make_deepseek(client)

    assert llm.rank_clauses(APP, CLAUSES) == ["CLS-1"]


def test_summarize_clauses_parses_and_filters():
    payload = {
        "summaries": [
            {"clause_id": "CLS-1", "summary": "归纳一"},
            {"clause_id": "CLS-2", "summary": "归纳二"},
            {"clause_id": "UNKNOWN", "summary": "忽略"},
            {"clause_id": "CLS-1", "summary": "   "},
        ]
    }
    llm = make_deepseek(fake_client(response_content=json.dumps(payload)))

    summaries = llm.summarize_clauses(APP, CLAUSES)

    assert {s.clause_id: s.summary for s in summaries} == {"CLS-1": "归纳一", "CLS-2": "归纳二"}


def test_suggest_missing_info_filters_non_strings():
    client = fake_client(response_content=json.dumps({"hints": ["缺少 X", "", 7]}))
    llm = make_deepseek(client)

    assert llm.suggest_missing_info(APP) == ["缺少 X"]


def test_chat_retries_transient_errors_then_raises():
    calls = []
    client = fake_client(error=RuntimeError("network down"), call_count_cb=lambda: calls.append(1))
    llm = make_deepseek(client)

    with pytest.raises(LLMError, match="重试 3 次"):
        llm.rank_clauses(APP, CLAUSES)
    assert len(calls) == 3


def test_chat_succeeds_after_transient_failure():
    attempts = []

    class FlakyCompletions:
        def create(self, **kwargs):
            attempts.append(1)
            if len(attempts) == 1:
                raise RuntimeError("network down")
            msg = SimpleNamespace(content=json.dumps({"relevant": ["CLS-1"]}))
            return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

    llm = DeepSeekLLM(api_key="k")
    llm._client = SimpleNamespace(chat=SimpleNamespace(completions=FlakyCompletions()))  # type: ignore[assignment]

    assert llm.rank_clauses(APP, CLAUSES) == ["CLS-1"]
    assert len(attempts) == 2


def test_chat_authentication_error_no_retry():
    import httpx

    calls = []
    response = httpx.Response(401, request=httpx.Request("POST", "https://api.deepseek.com"))
    error = AuthenticationError("bad key", response=response, body=None)
    client = fake_client(error=error, call_count_cb=lambda: calls.append(1))
    llm = make_deepseek(client)

    with pytest.raises(LLMError, match="鉴权失败"):
        llm.rank_clauses(APP, CLAUSES)
    assert len(calls) == 1


def test_chat_empty_content_raises_llm_error():
    llm = make_deepseek(fake_client(response_content=None))

    with pytest.raises(LLMError, match="空内容"):
        llm.suggest_missing_info(APP)


def test_rank_clauses_missing_relevant_key_raises():
    llm = make_deepseek(fake_client(response_content=json.dumps({"oops": []})))

    with pytest.raises(LLMError, match="格式错误"):
        llm.rank_clauses(APP, CLAUSES)


# ---------- 工厂 ----------


def test_factory_auto_without_key_returns_null():
    llm = build_llm(AppConfig(llm_provider="auto", deepseek_api_key=""))
    assert llm.name == "null"


def test_factory_auto_with_key_returns_deepseek():
    llm = build_llm(AppConfig(llm_provider="auto", deepseek_api_key="sk-test"))
    assert llm.name == "deepseek"


def test_factory_null_forced():
    llm = build_llm(AppConfig(llm_provider="null", deepseek_api_key="sk-test"))
    assert llm.name == "null"


def test_factory_deepseek_without_key_raises():
    with pytest.raises(LLMError, match="未配置"):
        build_llm(AppConfig(llm_provider="deepseek", deepseek_api_key=""))


def test_factory_unknown_provider_raises():
    with pytest.raises(LLMError, match="未知 LLM provider"):
        build_llm(AppConfig(llm_provider="gpt"))
