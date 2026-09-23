from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, Response

from opengwt.server.errors import AppError

router = APIRouter()


def _etag_response(request: Request, body: Any, etag: str) -> Response:
    if request.headers.get("if-none-match") == f'"{etag}"':
        return Response(status_code=304, headers={"ETag": f'"{etag}"'})
    from fastapi.responses import JSONResponse

    return JSONResponse(body, headers={"ETag": f'"{etag}"'})


@router.get("/content/pack")
async def pack(request: Request) -> Response:
    content = request.app.state.content
    return _etag_response(request, content.pack, content.pack_hash)


@router.get("/content/i18n")
async def locales(request: Request) -> dict[str, Any]:
    content = request.app.state.content
    return {"locales": list(content.renderer.locales), "pack_hash": content.pack_hash}


@router.get("/content/i18n/{locale}")
async def table(locale: str, request: Request) -> Response:
    content = request.app.state.content
    if locale not in content.i18n:
        raise AppError("locale_unsupported", 404, {"locale": locale})
    return _etag_response(request, content.i18n[locale], content.pack_hash)
