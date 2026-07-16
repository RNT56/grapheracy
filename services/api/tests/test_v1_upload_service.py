from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from starlette.datastructures import UploadFile

from graphview_api.api_v1.upload_service import UploadService, UploadUnavailableError, UploadValidationError


class RecordingJobs:
    def __init__(self) -> None:
        self.payload = None

    def enqueue(self, payload, *, project_id: str):
        self.payload = payload
        return {"id": "job-1", "project_id": project_id}


class RecordingObjectStore:
    def __init__(self) -> None:
        self.content = b""
        self.key = ""

    def put_file(self, key: str, path: Path, **_kwargs) -> None:
        self.key = key
        self.content = path.read_bytes()


def settings(*, max_bytes: int = 1024):
    return SimpleNamespace(
        upload_max_bytes=max_bytes,
        malware_scan_url=None,
        malware_scan_clamd_host=None,
        malware_scan_clamd_port=3310,
    )


@pytest.mark.anyio
async def test_v1_upload_service_streams_object_and_enqueues_checksum_bound_job() -> None:
    jobs = RecordingJobs()
    objects = RecordingObjectStore()
    service = UploadService(jobs, object_store=objects, settings=settings())
    upload = UploadFile(BytesIO(b"graph evidence"), filename="../evidence.txt", headers={"content-type": "text/plain"})

    result = await service.accept(upload, title=None, graph_id="project-1:graph", actor_id="user-1")

    assert result["job_id"] == "job-1"
    assert result["filename"] == "evidence.txt"
    assert objects.content == b"graph evidence"
    assert objects.key.startswith("project-1/uploads/")
    assert jobs.payload.idempotency_key == f"upload:project-1:{result['checksum']}"


@pytest.mark.anyio
async def test_v1_upload_service_rejects_unavailable_empty_and_oversized_uploads() -> None:
    unavailable = UploadService(RecordingJobs())
    with pytest.raises(UploadUnavailableError):
        await unavailable.accept(UploadFile(BytesIO(b"x"), filename="x.txt"), title=None, graph_id=None, actor_id="u")

    service = UploadService(RecordingJobs(), object_store=RecordingObjectStore(), settings=settings(max_bytes=1))
    with pytest.raises(UploadValidationError, match="empty"):
        await service.accept(UploadFile(BytesIO(b""), filename="empty.txt"), title=None, graph_id=None, actor_id="u")
    with pytest.raises(UploadValidationError) as raised:
        await service.accept(UploadFile(BytesIO(b"too big"), filename="large.txt"), title=None, graph_id=None, actor_id="u")
    assert raised.value.too_large is True
