# 系统详细设计

## 1. 领域模型（pydantic v2，`extra="forbid"`）

```text
Applicant        { role, organization_id, region }
Destination      { connector_id, region }
Evidence         { type, present=true, reference? }
SubscriptionApplication {
  application_id, applicant, purpose, purpose_description?,
  data_types[], data_fields[], destination, recipient,
  retention_days, requested_until (date), submitted_at (datetime),
  evidence[], policy_version?
}
PolicyRule       { rule_id, name, section, description, check, outcome_on_fail,
                   missing_outcome="manual_review", evidence_required[], clause_ref,
                   source, risk, reason }
Policy           { policy_id, version, effective_date, regions[], fail_closed=true, rules[] }
RuleResult       { rule_id, name, section, status(pass|violated|evidence_missing|risk_flag),
                   outcome(allow|deny|manual_review), reason, expected?, actual?,
                   clause_ref, source, risk, evidence_used[] }
VerdictReport    { application_id, verdict, policy_id, policy_version, matched_rules[],
                   evidence_used[], missing_information[], explanation?, llm_provider,
                   llm_used, assessed_at }
```

## 2. 策略 YAML 与检查类型（确定性核心）

策略文件 `knowledge_base/policies/*.yaml`，`version` 语义化（加载时取最高）。检查类型（`check.type`）：

| 类型 | 参数 | 语义 | 失败时 |
|------|------|------|--------|
| `allowlist` | path, values | 标量字段值 ∈ 白名单 | fail |
| `subset` | path, values | 列表字段值 ⊆ 白名单 | fail |
| `fields_within` | path, per_type | 每个请求字段至少属于一个请求数据类型的白名单 | fail |
| `lte` | path, max | 数值字段 ≤ 上限 | fail |
| `date_within` | path, anchor, min_days, max_days | 日期落在 [anchor+min, anchor+max] | fail |
| `evidence_present` | evidence_types, when{path,contains}? | when 命中时检查证据存在：存在→pass；缺失→missing；when 未命中→not_applicable | missing |
| `condition` | all_of[{path,op,value}] | 组合条件（用于风险规则） | fail |

`outcome_on_fail`: deny | manual_review；`missing_outcome`: deny（缺必要条件，如身份证明）| manual_review（信息不足，可补交）。

## 3. 判定优先级

```text
if any(matched.outcome == deny)           → DENY
elif any(matched.outcome == manual_review) → MANUAL_REVIEW
elif len(matched) == 0                    → MANUAL_REVIEW  (fail-closed，系统恒定行为)
else                                      → ALLOW
```

fail-closed 是**系统恒定行为**（无规则命中 → manual_review，绝不默认放行），不可被策略配置关闭。
策略加载期做参数完备性校验：检查类型缺少必填参数、when 守卫不完整、版本号非纯数字点分等一律拒绝加载，防止拼写错误导致规则静默失效（fail-open）。

## 4. 知识库

- 条款：`knowledge_base/clauses/*.md`，YAML frontmatter 含 `clause_id/title/region/data_types/keywords/source/summary/related_rules`。
- 本地检索：应用文本（用途/描述/数据类型/字段）与条款 keywords 词元重叠打分；引擎命中条款（clause_ref）强制包含。
- LLM 检索：对候选条款做语义相关性排序（辅助），失败降级本地打分。

## 5. LLM 层（辅助，无判定权）

- 协议 `LLMClient`：`rank_clauses(app, clauses) -> [clause_id]`；`summarize_clauses(app, clauses) -> [ClauseSummary]`；`suggest_missing_info(app) -> [str]`。
- `DeepSeekLLM`：OpenAI SDK，`base_url=https://api.deepseek.com`，模型默认 `deepseek-flash`（env 可换 `deepseek-v4-pro`），`response_format=json_object`，重试 3 次，空响应/非法 JSON → `LLMError`。
- `NullLLM`（默认降级）：条款 frontmatter `summary` 做模板归纳，本地打分排序，提示为空。
- provider 选择：`auto`（有 `DEEPSEEK_API_KEY` 用 deepseek，否则 null）| `null` | `deepseek`。

## 6. API（FastAPI）

统一响应信封 `{success, data, error, metadata}`，**成功与失败（422/404/500）均使用同一信封**（由异常处理器统一保证）：

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/v1/assess` | 评估申请；body=SubscriptionApplication，query `use_llm=false` 可关模型；请求体非法 → 422 信封 |
| GET | `/v1/policies` | 列出可用策略版本 |
| GET | `/v1/health` | 健康检查 |

边界校验（pydantic，extra=forbid）：retention_days 为非负整数（拒绝 bool 隐式转换）、data_types/data_fields 非空、submitted_at 无时区时视为 UTC。

## 7. CLI

```text
compliance-agent assess --application samples/app_allow.yaml [--policy-version 1.0.0] [--no-llm] [--output report.json]
compliance-agent policies
```
输出 JSON 报告（含 verdict 与全部四要素），`--output` 落盘。退出码恒为 0（判定本身非错误）。
