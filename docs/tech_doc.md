# 技术文档

## 1. 技术栈

| 项 | 选择 | 理由 |
|----|------|------|
| 语言 | Python ≥ 3.10 | 项目既定（pythonproject） |
| 校验 | pydantic v2（extra=forbid） | 边界输入校验，fail fast |
| 策略 | YAML + 自研确定性检查器 | 见下方"备选方案与取舍" |
| 服务 | FastAPI + uvicorn | 标准异步框架，OpenAPI 自带 |
| LLM | DeepSeek（OpenAI SDK，`https://api.deepseek.com`） | 用户指定；官方确认 OpenAI 兼容 + JSON 模式 |
| 测试 | pytest + pytest-cov（fail_under=80） | 覆盖单测/集成/E2E |

## 2. 安装与运行

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"            # 安装含测试依赖
pytest --cov=compliance_agent      # 全量测试 + 覆盖率

# CLI（无需 API Key 也能完整跑判定，用本地降级）
compliance-agent assess --application samples/app_allow.yaml
# 开启 DeepSeek 辅助检索/解释
export DEEPSEEK_API_KEY=sk-...
compliance-agent assess --application samples/app_manual_review.yaml

# FastAPI
uvicorn compliance_agent.api.app:app --reload
curl -X POST localhost:8000/v1/assess -H 'Content-Type: application/json' -d @samples/app_allow.json
```

## 3. 配置（环境变量 + 默认值）

| 变量 | 默认 | 说明 |
|------|------|------|
| `COMPLIANCE_KB_DIR` | 仓库根 `knowledge_base/` | 知识库目录（policies/ + clauses/） |
| `COMPLIANCE_LLM_PROVIDER` | `auto` | `auto` / `null` / `deepseek` |
| `DEEPSEEK_API_KEY` | 空 | 为空且 provider=auto → 降级 null |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | OpenAI 兼容端点 |
| `DEEPSEEK_MODEL` | `deepseek-flash` | 可换 `deepseek-v4-pro` |
| `DEEPSEEK_TIMEOUT` | `30` | 秒 |
| `DEEPSEEK_MAX_TOKENS` | `2048` | JSON 输出防截断 |

## 4. 备选方案与取舍（研究记录）

调研（GitHub/PyPI，2026-10）：
- [GuardianAngel](https://pypi.org/project/guardian-angel/)：YAML → allow/deny/require_approval，但 **first-match-wins + 默认放行**，与 fail-closed、deny 优先的审计语义相反。
- [AgentPolicyPack](https://socket.dev/pypi/package/agentpolicypack/overview/0.1.0a1)：有 `deny_overrides` 与 `require_review`，但为 alpha 版本，捆绑 agent 工具治理功能，与场景无关。
- [Microsoft AgentMesh governance](https://github.com/microsoft/agent-governance-toolkit)：语义接近（<5ms、冲突策略），但为 agent 治理平台组件，引入成本高。
- OPA/Cedar：功能远超所需，外部服务依赖，Rego/Cedar 学习成本。

**决策**：移植成熟语义（deny_overrides 冲突策略、fail-closed 默认拒绝、规则即理由、解释性决策），自研约 150 行确定性检查器——检查类型白名单制（7 种），无通用表达式求值器，保证可审计、可测试、零额外依赖。

## 5. 关键实现约束

- `verdict` 字段唯一写入点：`engine/verdict.py:decide()`（guardrail 测试锁定）。
- LLM 输出 JSON 解析：剥代码围栏、丢弃未知键、空内容按 LLMError 处理；LLM 层任何异常（含非 LLMError）都降级本地实现，判定不受影响。
- DeepSeek 认证错误（401）不重试直接抛出；其余错误重试 3 次（0.5s 退避）。
- 策略加载期校验参数完备性：检查类型缺必填参数、when 守卫不完整、版本号非纯数字点分 → 拒绝加载（防静默放行）。
- 显式指定策略版本时，目录中无关的损坏文件不影响该版本；取最新版本时任何损坏文件显式报错。
- 所有中文理由/条款以 UTF-8 存储；报告时间戳 UTC ISO8601。
- 知识库目录默认取源码树内 `knowledge_base/`；非源码安装（wheel）部署须设置 `COMPLIANCE_KB_DIR`。
