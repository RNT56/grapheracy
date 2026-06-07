from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str
    role: str


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
    "admin": {READ_PERMISSION, WRITE_PERMISSION, REVIEW_PERMISSION, OPERATE_PERMISSION},
}


async def get_current_user(x_graphview_user: str | None = Header(default="researcher")) -> CurrentUser:
    if x_graphview_user is None:
        return SEEDED_USERS["researcher"]

    user = SEEDED_USERS.get(x_graphview_user)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unknown local development user",
        )
    return user


def require_permission(permission: str):
    async def dependency(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if permission not in ROLE_PERMISSIONS.get(user.role, set()):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User is not authorized for this action",
            )
        return user

    return dependency
