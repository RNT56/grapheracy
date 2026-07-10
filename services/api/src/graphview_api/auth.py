from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Request, status

from graphview_api.settings import Settings, get_settings


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str
    role: str
    project_ids: tuple[str, ...] = ("*",)

    def can_access_project(self, project_id: str) -> bool:
        return "*" in self.project_ids or project_id in self.project_ids


READ_PERMISSION = "graph:read"
WRITE_PERMISSION = "graph:write"
REVIEW_PERMISSION = "review:write"
OPERATE_PERMISSION = "operate"


SEEDED_USERS = {
    "reader": CurrentUser(id="user-reader", email="reader@example.local", role="reader"),
    "researcher": CurrentUser(id="user-researcher", email="researcher@example.local", role="reviewer"),
    "maintainer": CurrentUser(id="user-maintainer", email="maintainer@example.local", role="admin"),
}

ROLE_PERMISSIONS = {
    "reader": {READ_PERMISSION},
    "reviewer": {READ_PERMISSION, WRITE_PERMISSION, REVIEW_PERMISSION},
    "service": {READ_PERMISSION, WRITE_PERMISSION, OPERATE_PERMISSION},
    "admin": {READ_PERMISSION, WRITE_PERMISSION, REVIEW_PERMISSION, OPERATE_PERMISSION},
}


async def get_current_user(
    request: Request,
    authorization: str | None = Header(default=None),
    x_graphview_user: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> CurrentUser:
    local_environment = settings.environment in {"local", "test", "development"}
    if local_environment and not authorization:
        user = SEEDED_USERS.get(x_graphview_user or "researcher")
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown local development user")
        return user

    identity = request.app.state.identity
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token required")
        try:
            return await identity.authenticate_bearer(token)
        except PermissionError as error:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
        except Exception as error:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid OIDC bearer token") from error

    session_id = request.cookies.get(settings.session_cookie_name)
    session = await identity.session(session_id) if session_id else None
    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return CurrentUser(**session["user"])


def require_permission(permission: str):
    async def dependency(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if permission not in ROLE_PERMISSIONS.get(user.role, set()):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User is not authorized for this action",
            )
        return user

    return dependency


def ensure_project_access(user: CurrentUser, project_id: str) -> None:
    if not user.can_access_project(project_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project resource not found")
