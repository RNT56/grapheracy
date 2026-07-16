from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from dataclasses import asdict
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from redis.asyncio import Redis

from graphview_api.auth import CurrentUser
from graphview_api.settings import Settings


class MemorySessionStore:
    def __init__(self) -> None:
        self._values: dict[str, tuple[float, dict[str, Any]]] = {}

    async def put(self, key: str, value: dict[str, Any], ttl: int) -> None:
        self._values[key] = (time.monotonic() + ttl, value)

    async def get(self, key: str) -> dict[str, Any] | None:
        item = self._values.get(key)
        if item is None:
            return None
        expires_at, value = item
        if expires_at <= time.monotonic():
            self._values.pop(key, None)
            return None
        return value

    async def delete(self, key: str) -> None:
        self._values.pop(key, None)

    async def close(self) -> None:
        return None

    async def ping(self) -> str:
        return "memory"


class RedisSessionStore:
    def __init__(self, redis_url: str) -> None:
        self.redis = Redis.from_url(redis_url, decode_responses=True)

    async def put(self, key: str, value: dict[str, Any], ttl: int) -> None:
        await self.redis.set(f"graphview:identity:{key}", json.dumps(value), ex=ttl)

    async def get(self, key: str) -> dict[str, Any] | None:
        value = await self.redis.get(f"graphview:identity:{key}")
        return json.loads(value) if value else None

    async def delete(self, key: str) -> None:
        await self.redis.delete(f"graphview:identity:{key}")

    async def close(self) -> None:
        await self.redis.aclose()

    async def ping(self) -> str:
        if not await self.redis.ping():
            raise ConnectionError("Redis session store did not acknowledge ping")
        return "redis"


class OIDCVerifier:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._discovery: tuple[float, dict[str, Any]] | None = None
        self._jwks: tuple[float, dict[str, Any]] | None = None

    async def discovery(self) -> dict[str, Any]:
        if not self.settings.oidc_issuer_url:
            raise ValueError("OIDC issuer is not configured")
        if self._discovery and self._discovery[0] > time.monotonic():
            return self._discovery[1]
        discovery_base = self.settings.oidc_backchannel_url or self.settings.oidc_issuer_url
        url = f"{discovery_base.rstrip('/')}/.well-known/openid-configuration"
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url)
            response.raise_for_status()
            document = response.json()
        if document.get("issuer") != self.settings.oidc_issuer_url.rstrip("/"):
            raise ValueError("OIDC discovery issuer mismatch")
        self._discovery = (time.monotonic() + 300, document)
        return document

    async def verify(self, token: str) -> dict[str, Any]:
        discovery = await self.discovery()
        if self._jwks and self._jwks[0] > time.monotonic():
            jwks = self._jwks[1]
        else:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(self.backchannel(discovery["jwks_uri"]))
                response.raise_for_status()
                jwks = response.json()
            self._jwks = (time.monotonic() + 300, jwks)
        header = jwt.get_unverified_header(token)
        key_document = next((key for key in jwks.get("keys", []) if key.get("kid") == header.get("kid")), None)
        if key_document is None:
            self._jwks = None
            raise ValueError("OIDC signing key not found")
        algorithm = str(header.get("alg") or "")
        if algorithm not in {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512"}:
            raise ValueError("OIDC token uses an unsupported signing algorithm")
        signing_key = jwt.PyJWK.from_dict(key_document, algorithm=algorithm).key
        audience = self.settings.oidc_audience or self.settings.oidc_client_id
        return jwt.decode(
            token,
            signing_key,
            algorithms=[algorithm],
            audience=audience,
            issuer=self.settings.oidc_issuer_url.rstrip("/"),
            options={"require": ["exp", "iat", "sub"]},
        )

    def backchannel(self, url: str) -> str:
        if not self.settings.oidc_backchannel_url or not self.settings.oidc_issuer_url:
            return url
        issuer = self.settings.oidc_issuer_url.rstrip("/")
        if url == issuer or url.startswith(f"{issuer}/"):
            return f"{self.settings.oidc_backchannel_url.rstrip('/')}{url[len(issuer):]}"
        return url


class IdentityService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store = MemorySessionStore() if settings.environment in {"local", "test", "development"} else RedisSessionStore(settings.arq_redis_url)
        self.verifier = OIDCVerifier(settings)

    def user_from_claims(self, claims: dict[str, Any]) -> CurrentUser:
        raw_groups = claims.get(self.settings.oidc_groups_claim, [])
        groups = {str(group) for group in raw_groups} if isinstance(raw_groups, list) else set()
        if self.settings.oidc_admin_group in groups:
            role = "admin"
        elif self.settings.oidc_service_group in groups:
            role = "service"
        elif self.settings.oidc_reviewer_group in groups:
            role = "reviewer"
        elif self.settings.oidc_reader_group in groups:
            role = "reader"
        else:
            raise PermissionError("OIDC principal has no Graphview role")
        project_ids = tuple(
            sorted(group.removeprefix(self.settings.oidc_project_group_prefix) for group in groups if group.startswith(self.settings.oidc_project_group_prefix))
        )
        if role in {"admin", "service"}:
            project_ids = ("*",)
        elif not project_ids:
            project_ids = ("project-default",)
        return CurrentUser(
            id=str(claims["sub"]),
            email=str(claims.get("email") or claims.get("preferred_username") or claims["sub"]),
            role=role,
            project_ids=project_ids,
        )

    async def authenticate_bearer(self, token: str) -> CurrentUser:
        return self.user_from_claims(await self.verifier.verify(token))

    async def ready(self) -> str:
        return await self.store.ping()

    async def session(self, session_id: str) -> dict[str, Any] | None:
        return await self.store.get(f"session:{session_id}")

    async def begin_login(self, return_to: str = "/") -> str:
        if not self.settings.oidc_client_id:
            raise ValueError("OIDC client is not configured")
        discovery = await self.verifier.discovery()
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        await self.store.put(
            f"state:{state}",
            {"verifier": verifier, "return_to": return_to if return_to.startswith("/") else "/"},
            600,
        )
        query = urlencode(
            {
                "client_id": self.settings.oidc_client_id,
                "redirect_uri": self.settings.oidc_redirect_uri,
                "response_type": "code",
                "scope": self.settings.oidc_scopes,
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
        return f"{discovery['authorization_endpoint']}?{query}"

    async def finish_login(self, *, code: str, state: str) -> tuple[str, str, str]:
        pending = await self.store.get(f"state:{state}")
        await self.store.delete(f"state:{state}")
        if pending is None:
            raise ValueError("OIDC login state is missing or expired")
        discovery = await self.verifier.discovery()
        form = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": self.settings.oidc_client_id,
            "redirect_uri": self.settings.oidc_redirect_uri,
            "code_verifier": pending["verifier"],
        }
        if self.settings.oidc_client_secret:
            form["client_secret"] = self.settings.oidc_client_secret
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(self.verifier.backchannel(discovery["token_endpoint"]), data=form)
            response.raise_for_status()
            tokens = response.json()
        claims = await self.verifier.verify(str(tokens.get("id_token") or tokens["access_token"]))
        user = self.user_from_claims(claims)
        session_id = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(32)
        await self.store.put(
            f"session:{session_id}",
            {"user": asdict(user), "csrf_token": csrf_token},
            self.settings.session_ttl_seconds,
        )
        return session_id, csrf_token, str(pending["return_to"])

    async def logout(self, session_id: str) -> None:
        await self.store.delete(f"session:{session_id}")
