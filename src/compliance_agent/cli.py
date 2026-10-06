"""命令行入口。

退出码约定：0 = 评估完成（allow/manual_review/deny 均为正常结果）；2 = 运行错误
（文件缺失、申请格式非法、策略版本不存在等）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

import yaml
from pydantic import ValidationError

from .engine.policy import PolicyError, list_policies
from .knowledge.clauses import ClauseError
from .models import SubscriptionApplication
from .service import ComplianceAssessor

EXIT_OK = 0
EXIT_ERROR = 2

# 可预期的运行错误：统一转成友好提示 + EXIT_ERROR，不抛裸 traceback
HANDLED_ERRORS = (ValueError, PolicyError, ClauseError, OSError)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="compliance-agent",
        description="跨境合规评估智能体：确定性策略引擎判定 + LLM 辅助检索/归纳/解释",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    assess_parser = subparsers.add_parser("assess", help="评估订阅申请")
    assess_parser.add_argument("--application", required=True, help="订阅申请 YAML 文件路径")
    assess_parser.add_argument("--policy-version", help="指定策略版本（默认取申请内期望版本或最新版）")
    assess_parser.add_argument("--no-llm", action="store_true", help="禁用模型辅助，仅用本地检索与模板解释")
    assess_parser.add_argument("--output", help="将报告 JSON 写入文件（缺省输出到 stdout）")

    subparsers.add_parser("policies", help="列出可用策略版本")
    return parser


def _load_application(path: Path) -> SubscriptionApplication:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"无法读取申请文件 {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"申请文件 {path} YAML 解析失败: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"申请文件 {path} 顶层必须是映射")
    try:
        return SubscriptionApplication.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(f"申请文件 {path} 内容不合法: {exc}") from exc


def _print_report(report_json: str, output: Optional[str]) -> None:
    if output:
        try:
            Path(output).write_text(report_json + "\n", encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"无法写入输出文件 {output}: {exc}") from exc
        print(f"报告已写入 {output}")
    else:
        print(report_json)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    assessor = ComplianceAssessor()

    if args.command == "policies":
        try:
            listing = list_policies(assessor.config.policies_dir)
        except PolicyError as exc:
            print(f"错误: {exc}", file=sys.stderr)
            return EXIT_ERROR
        print(json.dumps(listing, ensure_ascii=False, indent=2))
        return EXIT_OK

    # assess
    try:
        application = _load_application(Path(args.application))
        report = assessor.assess(
            application,
            policy_version=args.policy_version,
            use_llm=False if args.no_llm else None,
        )
        report_json = json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2)
        _print_report(report_json, args.output)
    except HANDLED_ERRORS as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return EXIT_ERROR
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
