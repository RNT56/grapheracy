from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import boto3

from graphview_api.settings import Settings


class LocalObjectStore:
    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        candidate = (self.root / key).resolve()
        if self.root not in candidate.parents:
            raise ValueError("Object key escapes configured storage root")
        return candidate

    def put_file(self, key: str, source: Path, *, content_type: str, checksum: str) -> None:
        destination = self._path(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)

    def get_bytes(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def put_bytes(self, key: str, payload: bytes, *, content_type: str, checksum: str) -> None:
        destination = self._path(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def create_multipart(self, key: str, *, content_type: str) -> str:
        upload_id = hashlib.sha256(f"local:{key}".encode("utf-8")).hexdigest()
        self._multipart_path(upload_id).mkdir(parents=True, exist_ok=True)
        return upload_id

    def upload_part(self, key: str, upload_id: str, part_number: int, payload: bytes) -> str:
        part = self._multipart_path(upload_id) / f"{part_number:08d}.part"
        part.write_bytes(payload)
        return hashlib.sha256(payload).hexdigest()

    def complete_multipart(self, key: str, upload_id: str, parts: list[dict]) -> None:
        destination = self._path(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".completing")
        with temporary.open("wb") as output:
            for part in parts:
                output.write((self._multipart_path(upload_id) / f"{int(part['part_number']):08d}.part").read_bytes())
        temporary.replace(destination)
        shutil.rmtree(self._multipart_path(upload_id), ignore_errors=True)

    def abort_multipart(self, key: str, upload_id: str) -> None:
        shutil.rmtree(self._multipart_path(upload_id), ignore_errors=True)
        self.delete(key)

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def ready(self) -> str:
        if not self.root.is_dir():
            raise FileNotFoundError("Local object-store root is unavailable")
        return "local"

    def _multipart_path(self, upload_id: str) -> Path:
        return self._path(f".multipart/{upload_id}")


class S3ObjectStore:
    def __init__(self, settings: Settings) -> None:
        self.bucket = settings.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            region_name=settings.s3_region,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
        )

    def put_file(self, key: str, source: Path, *, content_type: str, checksum: str) -> None:
        self.client.upload_file(
            str(source),
            self.bucket,
            key,
            ExtraArgs={"ContentType": content_type, "Metadata": {"sha256": checksum}},
        )

    def get_bytes(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def put_bytes(self, key: str, payload: bytes, *, content_type: str, checksum: str) -> None:
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=payload,
            ContentType=content_type,
            Metadata={"sha256": checksum},
        )

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def create_multipart(self, key: str, *, content_type: str) -> str:
        result = self.client.create_multipart_upload(Bucket=self.bucket, Key=key, ContentType=content_type)
        return str(result["UploadId"])

    def upload_part(self, key: str, upload_id: str, part_number: int, payload: bytes) -> str:
        result = self.client.upload_part(
            Bucket=self.bucket,
            Key=key,
            UploadId=upload_id,
            PartNumber=part_number,
            Body=payload,
        )
        return str(result["ETag"])

    def complete_multipart(self, key: str, upload_id: str, parts: list[dict]) -> None:
        self.client.complete_multipart_upload(
            Bucket=self.bucket,
            Key=key,
            UploadId=upload_id,
            MultipartUpload={"Parts": [{"ETag": part["etag"], "PartNumber": part["part_number"]} for part in parts]},
        )

    def abort_multipart(self, key: str, upload_id: str) -> None:
        self.client.abort_multipart_upload(Bucket=self.bucket, Key=key, UploadId=upload_id)

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except self.client.exceptions.ClientError as error:
            status = int(error.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0))
            if status == 404:
                return False
            raise

    def ready(self) -> str:
        self.client.head_bucket(Bucket=self.bucket)
        return "s3"


def build_object_store(settings: Settings):
    if settings.object_store_provider == "local":
        return LocalObjectStore(settings.object_store_path)
    if settings.object_store_provider == "s3":
        return S3ObjectStore(settings)
    raise ValueError(f"Unsupported object store provider: {settings.object_store_provider}")
