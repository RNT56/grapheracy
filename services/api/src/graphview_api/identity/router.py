from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse

from graphview_api.identity.service import IdentityService
from graphview_api.settings import Settings


def create_identity_router(identity: IdentityService, settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/v1/auth", tags=["Identity"])

    @router.get("/login")
    async def login(return_to: str = Query(default="/")):
        try:
            location = await identity.begin_login(return_to)
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
        return RedirectResponse(location, status_code=status.HTTP_302_FOUND)

    @router.get("/callback")
    async def callback(code: str, state: str):
        try:
            session_id, _, return_to = await identity.finish_login(code=code, state=state)
        except Exception as error:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="OIDC login failed") from error
        response = RedirectResponse(return_to, status_code=status.HTTP_303_SEE_OTHER)
        response.set_cookie(
            settings.session_cookie_name,
            session_id,
            max_age=settings.session_ttl_seconds,
            secure=settings.session_secure_cookie,
            httponly=True,
            samesite="lax",
            path="/",
        )
        return response

    @router.get("/session")
    async def session(request: Request):
        session_id = request.cookies.get(settings.session_cookie_name)
        value = await identity.session(session_id) if session_id else None
        if value is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
        return {"user": value["user"], "csrf_token": value["csrf_token"]}

    @router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
    async def logout(request: Request):
        session_id = request.cookies.get(settings.session_cookie_name)
        if session_id:
            await identity.logout(session_id)
        response = Response(status_code=status.HTTP_204_NO_CONTENT)
        response.delete_cookie(settings.session_cookie_name, path="/")
        return response

    return router
