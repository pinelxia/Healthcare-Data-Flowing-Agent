---
clause_id: CLS-MIN-001
title: 数据最小化与字段白名单
region: [cn-mainland, hk]
data_types: [diagnosis_summary, cost_detail, claim_certificate]
keywords: [最小化, 字段, 白名单, 必要, 授权]
source: 法律假设：数据最小化原则（参照个人信息保护一般框架，示意条款，非法律意见）
summary: 仅允许订阅三类必要数据，且字段须在按类型限定的白名单内；诊断类数据须附患者授权。
related_rules: [MIN-001, MIN-002, EVI-001]
---
# 数据最小化与字段白名单

1. 跨境订阅仅允许三类数据：就诊摘要（diagnosis_summary）、费用明细（cost_detail）、理赔证明（claim_certificate）。原始病历等其他数据一律拒绝。
2. 每类数据有字段白名单，申请请求的每个字段必须至少属于一个所请求类型的白名单：
   - 就诊摘要：patient_name、visit_date、diagnosis_code、diagnosis_summary、attending_dept；
   - 费用明细：patient_name、item_name、item_date、amount、currency、charge_code；
   - 理赔证明：patient_name、diagnosis_code、certificate_no、issue_date、certificate_summary。
3. 订阅诊断类数据必须附患者授权同意记录（consent_record）。缺失时信息不足，转人工审批；补充后可按策略重新评估。

> 字段白名单与授权要求为业务/法律假设的示意值，实际以正式合规评审为准。
