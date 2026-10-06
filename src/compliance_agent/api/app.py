"""FastAPI 应用工厂：统一响应信封 {success, data, error, metadata}。"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ..config import AppConfig
from ..engine.policy import PolicyError, PolicyNotFoundError
from ..knowledge.clauses import ClauseError
from ..service import ComplianceAssessor
from .routes import router

logger = logging.getLogger(__name__)


def _register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"success": False, "data": None, "error": f"请求校验失败: {exc.errors()}", "metadata": {}},
        )

    @app.exception_handler(PolicyNotFoundError)
    async def policy_not_found_handler(request: Request, exc: PolicyNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"success": False, "data": None, "error": str(exc), "metadata": {}})

    @app.exception_handler(PolicyError)
    async def policy_error_handler(request: Request, exc: PolicyError) -> JSONResponse:
        return JSONResponse(status_code=500, content={"success": False, "data": None, "error": str(exc), "metadata": {}})

    @app.exception_handler(ClauseError)
    async def clause_error_handler(request: Request, exc: ClauseError) -> JSONResponse:
        return JSONResponse(status_code=500, content={"success": False, "data": None, "error": str(exc), "metadata": {}})

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("未预期错误: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"success": False, "data": None, "error": "内部错误，详见服务日志", "metadata": {}},
        )


def create_app(config: Optional[AppConfig] = None) -> FastAPI:
    app = FastAPI(
        title="跨境合规评估智能体",
        description="确定性策略引擎判定 + LLM 辅助检索/归纳/解释；判定结果不可被模型绕过",
        version="0.1.0",
    )
    assessor = ComplianceAssessor(config)
    app.state.assessor = assessor
    app.include_router(router)
    _register_error_handlers(app)
    return app


# 供 `uvicorn compliance_agent.api.app:app` 直接启动
app = create_app()
