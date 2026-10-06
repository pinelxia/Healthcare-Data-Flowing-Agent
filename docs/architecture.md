# 架构设计

## 1. 总览

```
                 ┌──────────────┐        ┌─────────────────────┐
  订阅申请 ────▶ │  FastAPI/CLI │ ─────▶ │  ComplianceAssessor │
                 └──────────────┘        │   (编排层 service)   │
                                         └──────┬──────┬───────┘
                     ┌──────────────────────────┘      │
                     ▼                                 ▼
        ┌────────────────────────┐        ┌───────────────────────┐
        │ 确定性引擎（无 LLM）     │        │ 知识库 + LLM（辅助层）  │
        │ policy → checks →      │        │ clauses + retriever    │
        │ evaluator → verdict    │        │ DeepSeek 适配 / 本地降级│
        └────────────────────────┘        └───────────────────────┘
                     └──────────────────────────┬────────────────
                                                 ▼
                                          VerdictReport
                     (verdict 只由引擎写入；LLM 输出仅进入 explanation)
```

## 2. 核心分层

| 层 | 模块 | 职责 | 是否含 LLM |
|----|------|------|-----------|
| 接入层 | `api/`、`cli.py` | HTTP 接口 / 命令行，输入校验（系统边界） | 否 |
| 编排层 | `service.py` | 加载策略 → 评估 → 检索条款 → 生成报告；LLM 失败降级 | 是（可关闭） |
| 判定层 | `engine/` | 策略加载校验、检查执行、判定优先级。**唯一判定来源** | 否 |
| 知识层 | `knowledge/` | 条款加载、本地关键词检索（确定性兜底） | 否 |
| 模型层 | `llm/` | 语义检索排序、条款归纳、缺失提示（纯辅助） | 是 |
| 报告层 | `report.py` | 组装 VerdictReport；verdict 字段仅接受引擎结果 | 否 |

## 3. 数据流（一次评估）

1. 入口校验申请（pydantic，`extra=forbid`，字段/类型失败即 422/报错）。
2. 加载策略：申请指定版本 → 精确匹配；未指定 → 取最高版本。
3. **引擎评估**：逐条规则执行确定性检查，产出每条命中规则的状态（pass / violated / evidence_missing / risk_flag）与理由。
4. **判定优先级**：任一 deny → deny；否则任一 manual_review → manual_review；否则无规则命中（fail-closed）→ manual_review；否则 allow。
5. 知识检索：本地关键词打分排序条款；引擎命中条款强制包含；LLM 可用时做语义排序与归纳。
6. 组装报告：verdict 取引擎结果；explanation 附模型归纳与提示，标注"仅供参考"。

## 4. 防绕过边界（Guardrail）

- `VerdictReport.verdict` 只允许由 `engine/verdict.py:decide()` 的结果赋值；service 与 report 无任何其他写入点（测试锁定）。
- LLM 接口协议不含 verdict 字段；其 JSON 输出 schema 中无判定键，解析后丢弃未知键。
- LLM 异常（无 Key、超时、空响应、非法 JSON）→ 捕获 → 降级本地模板，判定不受影响。
- fail-closed：申请未命中任何规则 → manual_review，绝不默认放行。

## 5. 目录结构

```
src/compliance_agent/
├── config.py        # 配置（env + 默认值）
├── models.py        # 领域模型（申请/规则/结果/报告，pydantic v2）
├── service.py       # 编排层
├── report.py        # 报告组装
├── engine/          # 确定性引擎（policy/checks/evaluator/verdict）
├── knowledge/       # 条款加载与本地检索
├── llm/             # base/null/deepseek/explainer
├── api/             # FastAPI 应用与路由
└── cli.py           # 命令行
knowledge_base/      # policies/（YAML 策略）+ clauses/（Markdown 条款）
samples/             # 三个 Mock 申请（allow/manual_review/deny）
tests/               # unit / integration / e2e
docs/                # 规划与技术文档
```
