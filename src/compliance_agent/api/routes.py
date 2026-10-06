"""API 路由。

成功与失败均使用统一信封 {success, data, error, metadata}：
成功由本文件返回；失败（422/404/500）由 app.py 的异常处理器以同样信封返回。
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from ..engine.policy import list_policies
from ..models import SubscriptionApplication

router = APIRouter()


class ApiResponse(BaseModel):
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    metadata: dict = Field(default_factory=dict)


@router.get("/v1/health", response_model=ApiResponse)
def health(request: Request) -> ApiResponse:
    return ApiResponse(
        success=True,
        data={"status": "ok"},
        metadata={"llm_provider": request.app.state.assessor.llm.name, "engine": "deterministic"},
    )


@router.get("/v1/policies", response_model=ApiResponse)
def policies(request: Request) -> ApiResponse:
    listing = list_policies(request.app.state.assessor.config.policies_dir)
    return ApiResponse(success=True, data={"policies": listing})


@router.post("/v1/assess", response_model=ApiResponse)
def assess(
    application: SubscriptionApplication,
    request: Request,
    use_llm: Optional[bool] = Query(default=None, description="是否启用模型辅助；默认跟随配置（auto）"),
) -> ApiResponse:
    assessor = request.app.state.assessor
    report = assessor.assess(application, use_llm=use_llm)
    return ApiResponse(
        success=True,
        data=report.model_dump(mode="json"),
        metadata={"engine": "deterministic", "policy_version": report.policy_version},
    )
