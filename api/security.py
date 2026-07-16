import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Security, WebSocket, status
from fastapi.security import OAuth2PasswordBearer, SecurityScopes

from core.settings import get_settings

SCOPE_DESCRIPTIONS = {
    "task": "运行智能体任务",
    "files": "上传、下载和查看会话文件",
    "ragflow": "管理 RAGFlow 知识库和文档",
    "conversations": "查看和创建会话记录",
}

DEFAULT_SCOPES = list(SCOPE_DESCRIPTIONS.keys())

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/auth/token",
    scopes=SCOPE_DESCRIPTIONS,
    auto_error=False,
)


@dataclass(frozen=True)
class AuthenticatedUser:
    username: str
    scopes: list[str]


def _is_auth_enabled() -> bool:
    return get_settings().api_auth_enabled


def _token_secret() -> bytes:
    return get_settings().api_auth_secret.encode("utf-8")


def _token_expire_seconds() -> int:
    return get_settings().api_token_expire_minutes * 60


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(f"{data}{padding}")


def _json_b64(data: dict[str, Any]) -> str:
    return _b64url_encode(json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def create_access_token(user: AuthenticatedUser) -> tuple[str, int]:
    now = int(time.time())
    expires_in = _token_expire_seconds()
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": user.username,
        "scope": " ".join(user.scopes),
        "iat": now,
        "exp": now + expires_in,
    }
    signing_input = f"{_json_b64(header)}.{_json_b64(payload)}"
    signature = hmac.new(_token_secret(), signing_input.encode("ascii"), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url_encode(signature)}", expires_in


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        header_raw, payload_raw, signature_raw = token.split(".", 2)
        signing_input = f"{header_raw}.{payload_raw}"
        expected_signature = hmac.new(_token_secret(), signing_input.encode("ascii"), hashlib.sha256).digest()
        actual_signature = _b64url_decode(signature_raw)
        if not hmac.compare_digest(expected_signature, actual_signature):
            raise ValueError("invalid signature")
        payload = json.loads(_b64url_decode(payload_raw))
        if int(payload.get("exp", 0)) < int(time.time()):
            raise ValueError("token expired")
        return payload
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error


async def check_rbac(
    security_scopes: SecurityScopes,
    token: str | None = Security(oauth2_scheme),
) -> AuthenticatedUser:
    """校验登录态和接口所需 scope，路由中可用 Security(check_rbac, scopes=[...])。"""
    if not _is_auth_enabled():
        return AuthenticatedUser(username="local-dev", scopes=DEFAULT_SCOPES)

    authenticate_header = "Bearer"
    if security_scopes.scopes:
        authenticate_header = f'Bearer scope="{security_scopes.scope_str}"'
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": authenticate_header},
    )
    if not token:
        raise credentials_exception

    payload = decode_access_token(token)
    username = str(payload.get("sub") or "")
    token_scopes = str(payload.get("scope") or "").split()
    if not username:
        raise credentials_exception

    missing_scopes = [scope for scope in security_scopes.scopes if scope not in token_scopes]
    if missing_scopes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Not enough permissions: {', '.join(missing_scopes)}",
        )
    return AuthenticatedUser(username=username, scopes=token_scopes)


async def require_websocket_token(websocket: WebSocket) -> bool:
    if not _is_auth_enabled():
        return True
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Missing access token")
        return False
    try:
        decode_access_token(token)
        return True
    except HTTPException:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid access token")
        return False
