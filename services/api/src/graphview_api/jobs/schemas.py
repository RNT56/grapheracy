from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


JobStatus = Literal["queued", "leased", "running", "retry", "succeeded", "failed", "cancelled"]


class JobCreate(BaseModel):
    kind: str = Field(min_length=1, max_length=120)
    queue: str = Field(default="default", min_length=1, max_length=80)
    idempotency_key: str = Field(min_length=1, max_length=240)
    payload: dict[str, Any] = Field(default_factory=dict)
    max_attempts: int = Field(default=5, ge=1, le=20)


class JobOut(BaseModel):
    id: str
    project_id: str
    queue: str
    kind: str
    status: JobStatus
    idempotency_key: str
    payload: dict[str, Any]
    result: dict[str, Any]
    attempt: int
    max_attempts: int
    available_at: datetime
    leased_until: datetime | None = None
    worker_id: str | None = None
    error_code: str | None = None
    error: str | None = None
    trace_id: str
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None = None


class JobPage(BaseModel):
    jobs: list[JobOut]
    next_cursor: str | None = None
