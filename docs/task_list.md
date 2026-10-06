# 任务清单

- [x] T0 研究：DeepSeek API 文档确认（OpenAI 兼容/JSON 模式）；策略引擎备选方案调研
- [x] T1 规划文档：PRD / assumptions / architecture / system_design / tech_doc
- [x] T2 项目骨架：pyproject、src 布局、.gitignore、venv 依赖
- [x] T3 领域模型：models.py（申请/策略/结果/报告，pydantic v2 + 边界约束）
- [x] T4 确定性引擎：policy 加载校验 → checks（7 种检查类型）→ evaluator → verdict 优先级
- [x] T5 知识库：7 篇 Markdown 条款 + 策略 YAML v1.0.0；本地关键词检索
- [x] T6 LLM 层：LLMClient 协议 / NullLLM / DeepSeekLLM / explainer；防绕过测试
- [x] T7 编排层：service.py + report.py（verdict 仅引擎写入）
- [x] T8 接入层：FastAPI（/v1/assess、/v1/policies、/v1/health）+ CLI（assess/policies）
- [x] T9 Mock 样例：allow / manual_review / deny 三个申请（YAML + JSON）
- [x] T10 测试：129 个测试（unit + integration + e2e），覆盖率 94%（≥80%）
- [x] T11 代码评审：15 项实证问题全部修复（防静默放行、fail-closed 恒定、信封统一、降级完备）
- [x] T12 README 与交付说明
