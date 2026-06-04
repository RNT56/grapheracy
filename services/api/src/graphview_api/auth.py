from dataclasses import dataclass

from fastapi import Header, HTTPException, status


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str
    role: str


SEEDED_USERS = {
    "researcher": CurrentUser(id="user-researcher", email="researcher@example.local", role="reviewer"),
    "maintainer": CurrentUser(id="user-maintainer", email="maintainer@example.local", role="admin"),
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
