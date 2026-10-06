"""FastAPI 应用工厂：统一响应信封 {success, data, error, metadata}。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ..config import AppConfig
from ..engine.policy import PolicyError, PolicyNotFoundError
from ..knowledge.clauses import ClauseError
from ..service import ComplianceAssessor
from .routes import router

logger = logging.getLogger(__name__)

# Swagger UI 资源本地化（随包分发）：不依赖外部 CDN，离线可用
_STATIC_DIR = Path(__file__).resolve().parent / "static"


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
    # FastAPI 0.142+ 不再接受 swagger_ui_js_url 等构造参数，内置 /docs 恒用 CDN；
    # 关闭内置版本，自行注册本地资源版（镜像 FastAPI 内部实现，见 fastapi/applications.py）
    app = FastAPI(
        title="跨境合规评估智能体",
        description="确定性策略引擎判定 + LLM 辅助检索/归纳/解释；判定结果不可被模型绕过",
        version="0.1.0",
        docs_url=None,
    )
    assessor = ComplianceAssessor(config)
    app.state.assessor = assessor
    app.include_router(router)
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    if app.openapi_url:

        @app.get("/docs", include_in_schema=False)
        async def swagger_ui_html(request: Request) -> HTMLResponse:
            root_path = request.scope.get("root_path", "").rstrip("/")
            response = get_swagger_ui_html(
                openapi_url=root_path + app.openapi_url,
                title=f"{app.title} - Swagger UI",
                swagger_js_url="/static/swagger-ui-bundle.js",
                swagger_css_url="/static/swagger-ui.css",
                swagger_favicon_url="/static/favicon.png",
                swagger_ui_parameters=app.swagger_ui_parameters,
            )
            response.headers["Cache-Control"] = "no-store"
            return response

    _register_error_handlers(app)
    return app


# 供 `uvicorn compliance_agent.api.app:app` 直接启动
app = create_app()
