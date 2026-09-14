"""Thin local-lab accounts (G6). Intention from dsl-backend localAuth.

Not Cognito. Not MFA TOTP. Not SaaS admin RBAC. Passwords are
pbkdf2-hmac-sha256. Tokens are HMAC-SHA256 JWT-style (stdlib only).
Users live in process memory and disappear on restart.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any

from dsl.errors import (
    AccountExists,
    InvalidCredentials,
    InvalidEmail,
    MissingCredentials,
    Unauthorized,
    WeakPassword,
)

SEED_EMAIL = "guy.payeur@gp2.ca"
SEED_NAME = "Guy Payeur"
DEFAULT_SEED_PASSWORD = "admin123!"
TOKEN_TTL_SEC = 24 * 3600
PBKDF2_ITERATIONS = 100_000
KEYLEN = 32
SALT_BYTES = 16
EMAIL_SHAPE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def looks_like_email(email: str) -> bool:
    return bool(EMAIL_SHAPE.fullmatch(email))


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def hash_password(password: str, salt: bytes, iterations: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations, dklen=KEYLEN)


def extract_bearer(headers: dict[str, str] | None) -> str | None:
    if not headers:
        return None
    raw = headers.get("authorization") or headers.get("Authorization")
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    kind, _, token = text.partition(" ")
    if kind.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


@dataclass(frozen=True)
class PublicUser:
    email: str
    name: str
    sub: str

    def to_dict(self) -> dict[str, str]:
        return {"email": self.email, "name": self.name, "sub": self.sub}


@dataclass
class StoredUser:
    email: str
    name: str
    sub: str
    salt: bytes
    password_hash: bytes
    iterations: int


class LocalAuth:
    """In-process local-lab accounts + HMAC tokens. No Cognito, no roles."""

    def __init__(
        self,
        *,
        secret: bytes | str | None = None,
        seed_email: str | None = None,
        seed_password: str | None = None,
        seed_name: str | None = None,
        iterations: int = PBKDF2_ITERATIONS,
        token_ttl_sec: int = TOKEN_TTL_SEC,
        clock: Any | None = None,
    ) -> None:
        if isinstance(secret, str):
            secret = secret.encode("utf-8")
        self.secret = secret or secrets.token_bytes(32)
        self.iterations = max(int(iterations), 1)
        self.token_ttl_sec = int(token_ttl_sec)
        self._clock = clock or time.time
        self._lock = threading.RLock()
        self._users: dict[str, StoredUser] = {}
        email = normalize_email(seed_email or SEED_EMAIL)
        password = seed_password if seed_password is not None else DEFAULT_SEED_PASSWORD
        name = (seed_name or SEED_NAME).strip() or email.split("@")[0]
        self.ensure_seed(email, password, name)

    @classmethod
    def from_env(cls) -> LocalAuth:
        secret = (os.environ.get("DSL_AUTH_SECRET") or "").strip() or None
        return cls(
            secret=secret,
            seed_email=(os.environ.get("DSL_SEED_EMAIL") or "").strip() or None,
            seed_password=(os.environ.get("DSL_SEED_PASSWORD") or "").strip() or None,
            seed_name=(os.environ.get("DSL_SEED_NAME") or "").strip() or None,
        )

    def ensure_seed(self, email: str, password: str, name: str) -> PublicUser:
        key = normalize_email(email)
        with self._lock:
            existing = self._users.get(key)
            if existing is not None:
                return PublicUser(email=existing.email, name=existing.name, sub=existing.sub)
            user = self._make_user(key, password, name)
            self._users[key] = user
            return PublicUser(email=user.email, name=user.name, sub=user.sub)

    def login(self, email: str, password: str) -> dict[str, Any]:
        key = normalize_email(email)
        if not key or not password:
            raise MissingCredentials()
        with self._lock:
            row = self._users.get(key)
            if row is None or not self._verify_password(password, row):
                raise InvalidCredentials()
            public = PublicUser(email=row.email, name=row.name, sub=row.sub)
        return self.issue_session(public)

    def register(self, email: str, password: str, name: str | None = None) -> dict[str, Any]:
        key = normalize_email(email)
        if not key or not looks_like_email(key):
            raise InvalidEmail(email)
        if not password or len(password) < 8:
            raise WeakPassword()
        display = (name or "").strip() or key.split("@")[0]
        with self._lock:
            if key in self._users:
                raise AccountExists(key)
            row = self._make_user(key, password, display)
            self._users[key] = row
            public = PublicUser(email=row.email, name=row.name, sub=row.sub)
        return self.issue_session(public)

    def issue_session(self, user: PublicUser, *, ttl_sec: int | None = None) -> dict[str, Any]:
        ttl = self.token_ttl_sec if ttl_sec is None else int(ttl_sec)
        now = int(self._clock())
        expires_at = now + ttl
        token = self._sign(
            {
                "sub": user.sub,
                "email": user.email,
                "name": user.name,
                "iat": now,
                "exp": expires_at,
            }
        )
        return {
            "user": user.to_dict(),
            "tokens": {
                "idToken": token,
                "accessToken": token,
                "refreshToken": token,
                "expiresAt": expires_at,
            },
        }

    def authenticate(self, headers: dict[str, str] | None) -> PublicUser:
        token = extract_bearer(headers)
        if token is None:
            raise Unauthorized()
        return self.verify_token(token)

    def verify_token(self, token: str) -> PublicUser:
        try:
            payload = self._decode(token)
        except Unauthorized:
            raise
        except Exception as exc:
            raise Unauthorized("invalid token") from exc
        sub = payload.get("sub")
        email = payload.get("email")
        if not isinstance(sub, str) or not sub or not isinstance(email, str):
            raise Unauthorized("invalid token")
        with self._lock:
            row = next((u for u in self._users.values() if u.sub == sub), None)
        if row is None:
            raise Unauthorized("unknown account")
        return PublicUser(email=row.email, name=row.name, sub=row.sub)

    def _make_user(self, email: str, password: str, name: str) -> StoredUser:
        salt = secrets.token_bytes(SALT_BYTES)
        return StoredUser(
            email=email,
            name=name,
            sub=str(uuid.uuid4()),
            salt=salt,
            password_hash=hash_password(password, salt, self.iterations),
            iterations=self.iterations,
        )

    def _verify_password(self, password: str, row: StoredUser) -> bool:
        actual = hash_password(password, row.salt, row.iterations)
        if len(actual) != len(row.password_hash):
            return False
        return hmac.compare_digest(actual, row.password_hash)

    def _sign(self, payload: dict[str, Any]) -> str:
        header = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
        body = _b64url_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
        signing = f"{header}.{body}".encode("ascii")
        sig = _b64url_encode(hmac.new(self.secret, signing, hashlib.sha256).digest())
        return f"{header}.{body}.{sig}"

    def _decode(self, token: str) -> dict[str, Any]:
        parts = token.split(".")
        if len(parts) != 3:
            raise Unauthorized("invalid token")
        header_b, body_b, sig_b = parts
        try:
            header = json.loads(_b64url_decode(header_b))
        except (ValueError, json.JSONDecodeError) as exc:
            raise Unauthorized("invalid token") from exc
        if not isinstance(header, dict) or header.get("alg") != "HS256":
            raise Unauthorized("invalid token")
        expected = hmac.new(
            self.secret, f"{header_b}.{body_b}".encode("ascii"), hashlib.sha256
        ).digest()
        try:
            given = _b64url_decode(sig_b)
        except ValueError as exc:
            raise Unauthorized("invalid token") from exc
        if len(given) != len(expected) or not hmac.compare_digest(given, expected):
            raise Unauthorized("invalid token")
        try:
            payload = json.loads(_b64url_decode(body_b))
        except (ValueError, json.JSONDecodeError) as exc:
            raise Unauthorized("invalid token") from exc
        if not isinstance(payload, dict):
            raise Unauthorized("invalid token")
        exp = payload.get("exp")
        if not isinstance(exp, int) or int(self._clock()) >= exp:
            raise Unauthorized("token expired")
        return payload
