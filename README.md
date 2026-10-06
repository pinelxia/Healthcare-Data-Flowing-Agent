# 跨境合规评估智能体

香港居民内地就医理赔场景下的**跨境数据订阅合规评估**组件：对订阅申请输出三态判定
`allow / manual_review / deny`，且每次判定返回命中的规则、使用的证据、缺失的信息与策略版本。

**核心原则：判定权在确定性策略引擎，LLM（DeepSeek）仅辅助检索、归纳与解释，不能绕过确定性规则直接放行。**
项目背景见 [background.txt](background.txt)，法律/业务假设与系统边界见 [docs/assumptions.md](docs/assumptions.md)。

## 快速开始

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# CLI 评估（无需 API Key：LLM 自动降级本地检索 + 模板解释，判定不受影响）
compliance-agent assess --application samples/app_allow.yaml          # → allow
compliance-agent assess --application samples/app_manual_review.yaml  # → manual_review
compliance-agent assess --application samples/app_deny.yaml           # → deny
compliance-agent policies                                             # 列出策略版本

# 启用 DeepSeek 辅助检索/解释（可选）
export DEEPSEEK_API_KEY=sk-...

# FastAPI 服务
uvicorn compliance_agent.api.app:app --reload
curl -X POST localhost:8000/v1/assess -H 'Content-Type: application/json' -d @samples/app_allow.json
```

## 三态判定

| 判定 | 含义 | 触发示例 |
|------|------|---------|
| `allow` | 满足条件，可继续交付 | 全部规则通过 |
| `manual_review` | 信息不足或风险较高，需人工审批 | 缺患者授权记录；诊断数据保留 >30 天 |
| `deny` | 违反策略或缺少必要条件，禁止交付 | 用途为营销；字段超出最小化白名单；保存期限超限 |

优先级 **deny > manual_review > allow**；无规则命中时 fail-closed → manual_review（恒定行为，不可关闭）。

## 架构

```
订阅申请 → FastAPI/CLI → ComplianceAssessor（编排）
                          ├─ 确定性引擎（policy→checks→evaluator→verdict）★唯一判定来源
                          ├─ 知识库（YAML 策略 + Markdown 条款，本地关键词检索兜底）
                          └─ LLM 辅助层（DeepSeek 检索排序/归纳/缺失提示，失败自动降级）
                          → VerdictReport（命中规则/证据/缺失信息/策略版本/解释）
```

详细设计见 [docs/](docs/)：PRD、架构、系统设计、技术文档、任务清单。

## 判定报告示例（samples/app_manual_review.yaml）

```json
{
  "application_id": "APP-DEMO-MANUAL-001",
  "verdict": "manual_review",
  "policy_id": "hk-mainland-crossborder",
  "policy_version": "1.0.0",
  "matched_rules": [
    {"rule_id": "EVI-001", "status": "evidence_missing", "outcome": "manual_review",
     "reason": "缺少患者授权同意记录，信息不足，需人工审批",
     "clause_ref": "clauses/data-minimization.md#CLS-MIN-001", "source": "法律假设 L2：..."}
  ],
  "evidence_used": [{"type": "identity_cert", "reference": "REG-HK-2026-0001", "rule_ids": ["ID-003"]}],
  "missing_information": ["[EVI-001] 患者授权同意记录：缺少患者授权同意记录...（期望: 提供证据: ['consent_record']；实际: 缺失: ['consent_record']）"],
  "explanation": "以下内容由模型辅助生成，仅供参考...",
  "llm_provider": "null", "llm_used": false
}
```

## 测试

```bash
pytest --cov=compliance_agent   # 129 个测试，覆盖率 ≥ 94%（要求 80%）
```

覆盖：7 种确定性检查类型、判定优先级、fail-closed、**LLM 无法篡改判定**（guardrail 测试锁定）、
LLM 故障降级、API 信封一致性、CLI 三条路径端到端、输入边界校验。

## 配置

| 环境变量 | 默认 | 说明 |
|----------|------|------|
| `COMPLIANCE_KB_DIR` | 源码树 `knowledge_base/` | 知识库目录（wheel 部署须显式设置） |
| `COMPLIANCE_LLM_PROVIDER` | `auto` | `auto` / `null` / `deepseek` |
| `DEEPSEEK_API_KEY` | 空 | 为空时 auto 降级本地实现 |
| `DEEPSEEK_MODEL` | `deepseek-flash` | 可换 `deepseek-v4-pro` |

> 本项目不提供正式法律意见；全部规则、名单与阈值为业务/法律假设的示意值，Mock 数据驱动，详见 [docs/assumptions.md](docs/assumptions.md)。
