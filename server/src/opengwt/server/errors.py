"""Application errors carry a code, a message key and parameters; the response also carries a
sentence rendered on the server in the negotiated locale (docs/protocol/match.md §2, i18n.md §8)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from opengwt.i18n import Param, Renderer, negotiate_locale


class AppError(Exception):
    def __init__(
        self,
        code: str,
        status: int = 400,
        params: Mapping[str, Param] | None = None,
        details: Any = None,
        message_key: str | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.status = status
        self.params: dict[str, Param] = dict(params or {})
        self.details = details
        self.message_key = message_key or "error." + code.replace("_", "-")


def error_body(renderer: Renderer, locale: str, error: AppError) -> dict[str, Any]:
    body: dict[str, Any] = {
        "code": error.code,
        "message_key": error.message_key,
        "params": error.params,
        "message": renderer.render(locale, error.message_key, error.params),
    }
    if error.details is not None:
        body["details"] = error.details
    return body


def request_locale(request: Request) -> str:
    renderer: Renderer = request.app.state.renderer
    locale = getattr(request.state, "locale", None)
    if isinstance(locale, str):
        return locale
    return negotiate_locale(renderer.locales, None, request.headers.get("accept-language"))


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, error: AppError) -> JSONResponse:
        renderer: Renderer = request.app.state.renderer
        return JSONResponse(
            status_code=error.status,
            content={"error": error_body(renderer, request_locale(request), error)},
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, error: RequestValidationError) -> JSONResponse:
        renderer: Renderer = request.app.state.renderer
        app_error = AppError("invalid_request", 422, details=error.errors())
        return JSONResponse(
            status_code=422,
            content={"error": error_body(renderer, request_locale(request), app_error)},
        )
