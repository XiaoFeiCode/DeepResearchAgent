import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timezone

from sqlalchemy import Column, String
from sqlmodel import Field, Session, SQLModel, select

from api.security import AuthenticatedUser, DEFAULT_SCOPES, SCOPE_DESCRIPTIONS
from core.settings import get_settings
from tools.database.mysql import get_engine

logger = logging.getLogger(__name__)

PASSWORD_HASH_ITERATIONS = 260_000


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class RBACUser(SQLModel, table=True):
    __tablename__ = "agent_rbac_users"

    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(sa_column=Column(String(64), unique=True, index=True, nullable=False))
    password_hash: str = Field(max_length=255, nullable=False)
    is_active: bool = Field(default=True, nullable=False)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
    updated_at: datetime = Field(default_factory=utc_now, nullable=False)


class RBACRole(SQLModel, table=True):
    __tablename__ = "agent_rbac_roles"

    id: int | None = Field(default=None, primary_key=True)
    code: str = Field(sa_column=Column(String(64), unique=True, index=True, nullable=False))
    name: str = Field(max_length=100, nullable=False)
    description: str = Field(default="", max_length=255)


class RBACPermission(SQLModel, table=True):
    __tablename__ = "agent_rbac_permissions"

    id: int | None = Field(default=None, primary_key=True)
    code: str = Field(sa_column=Column(String(64), unique=True, index=True, nullable=False))
    description: str = Field(default="", max_length=255)


class RBACUserRole(SQLModel, table=True):
    __tablename__ = "agent_rbac_user_roles"

    user_id: int = Field(foreign_key="agent_rbac_users.id", primary_key=True)
    role_id: int = Field(foreign_key="agent_rbac_roles.id", primary_key=True)


class RBACRolePermission(SQLModel, table=True):
    __tablename__ = "agent_rbac_role_permissions"

    role_id: int = Field(foreign_key="agent_rbac_roles.id", primary_key=True)
    permission_id: int = Field(foreign_key="agent_rbac_permissions.id", primary_key=True)


def hash_password(password: str, salt: str | None = None) -> str:
    """使用 PBKDF2 生成密码哈希，数据库中不保存明文密码。"""
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PASSWORD_HASH_ITERATIONS,
    ).hex()
    return f"pbkdf2_sha256${PASSWORD_HASH_ITERATIONS}${salt}${digest}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations_raw, salt, expected_digest = password_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            int(iterations_raw),
        ).hex()
        return hmac.compare_digest(digest, expected_digest)
    except Exception:
        return False


class AuthService:
    """MySQL 版 RBAC：用户 -> 角色 -> 权限 scope。"""

    def __init__(self) -> None:
        self._engine = None
        self.initialization_error: str | None = None

    @property
    def available(self) -> bool:
        return self._engine is not None and self.initialization_error is None

    def initialize(self) -> None:
        try:
            self._engine = get_engine()
            SQLModel.metadata.create_all(self._engine)
            self._seed_rbac_data()
            self.initialization_error = None
        except Exception as error:
            self._engine = None
            self.initialization_error = str(error)
            logger.warning("MySQL RBAC auth is unavailable: %s", error)

    def authenticate_user(self, username: str, password: str) -> AuthenticatedUser | None:
        engine = self._require_engine()
        with Session(engine) as session:
            user = session.exec(select(RBACUser).where(RBACUser.username == username)).first()
            if user is None or not user.is_active:
                return None
            if not verify_password(password, user.password_hash):
                return None
            scopes = self._get_user_scopes(session, user.id)
            return AuthenticatedUser(username=user.username, scopes=scopes)

    def list_rbac_snapshot(self) -> dict:
        engine = self._require_engine()
        with Session(engine) as session:
            users = session.exec(select(RBACUser).order_by(RBACUser.username)).all()
            roles = session.exec(select(RBACRole).order_by(RBACRole.code)).all()
            permissions = session.exec(select(RBACPermission).order_by(RBACPermission.code)).all()
            return {
                "users": [
                    {
                        "id": user.id,
                        "username": user.username,
                        "is_active": user.is_active,
                        "roles": self._get_user_role_codes(session, user.id),
                        "scopes": self._get_user_scopes(session, user.id),
                    }
                    for user in users
                ],
                "roles": [
                    {
                        "id": role.id,
                        "code": role.code,
                        "name": role.name,
                        "description": role.description,
                        "scopes": self._get_role_permission_codes(session, role.id),
                    }
                    for role in roles
                ],
                "permissions": [
                    {
                        "id": permission.id,
                        "code": permission.code,
                        "description": permission.description,
                    }
                    for permission in permissions
                ],
            }

    def _seed_rbac_data(self) -> None:
        engine = self._require_engine()
        with Session(engine) as session:
            permissions = self._ensure_permissions(session)
            roles = self._ensure_roles(session, permissions)
            self._ensure_demo_users(session, roles)
            session.commit()

    def _ensure_permissions(self, session: Session) -> dict[str, RBACPermission]:
        permissions: dict[str, RBACPermission] = {}
        for code, description in SCOPE_DESCRIPTIONS.items():
            permission = session.exec(select(RBACPermission).where(RBACPermission.code == code)).first()
            if permission is None:
                permission = RBACPermission(code=code, description=description)
                session.add(permission)
                session.flush()
            elif permission.description != description:
                permission.description = description
                session.add(permission)
            permissions[code] = permission
        return permissions

    def _ensure_roles(
        self,
        session: Session,
        permissions: dict[str, RBACPermission],
    ) -> dict[str, RBACRole]:
        role_defs = {
            "admin": {
                "name": "系统管理员",
                "description": "拥有所有 API 权限",
                "scopes": DEFAULT_SCOPES,
            },
            "researcher": {
                "name": "研究员",
                "description": "可以运行任务、查看文件和会话",
                "scopes": ["task", "files", "image_knowledge", "conversations"],
            },
            "knowledge_manager": {
                "name": "知识库管理员",
                "description": "可以管理 RAGFlow、图片知识库和会话文件",
                "scopes": ["ragflow", "image_knowledge", "files", "conversations"],
            },
            "viewer": {
                "name": "只读观察者",
                "description": "只能查看会话和文件",
                "scopes": ["files", "conversations"],
            },
        }
        roles: dict[str, RBACRole] = {}
        for code, role_def in role_defs.items():
            role = session.exec(select(RBACRole).where(RBACRole.code == code)).first()
            if role is None:
                role = RBACRole(code=code, name=role_def["name"], description=role_def["description"])
                session.add(role)
                session.flush()
            else:
                role.name = role_def["name"]
                role.description = role_def["description"]
                session.add(role)
            roles[code] = role
            self._sync_role_permissions(session, role.id, [permissions[scope].id for scope in role_def["scopes"]])
        return roles

    def _ensure_demo_users(self, session: Session, roles: dict[str, RBACRole]) -> None:
        settings = get_settings()
        users = [
            (settings.api_admin_username, settings.api_admin_password, "admin"),
        ]
        if settings.api_seed_demo_users:
            users.extend(
                [
                    ("researcher", "researcher123456", "researcher"),
                    ("kb_manager", "kb123456", "knowledge_manager"),
                    ("viewer", "viewer123456", "viewer"),
                ]
            )

        for username, password, role_code in users:
            user = session.exec(select(RBACUser).where(RBACUser.username == username)).first()
            if user is None:
                user = RBACUser(username=username, password_hash=hash_password(password))
                session.add(user)
                session.flush()
            self._ensure_user_role(session, user.id, roles[role_code].id)

    def _sync_role_permissions(
        self,
        session: Session,
        role_id: int | None,
        permission_ids: list[int | None],
    ) -> None:
        if role_id is None:
            return
        desired = {permission_id for permission_id in permission_ids if permission_id is not None}
        existing = session.exec(
            select(RBACRolePermission).where(RBACRolePermission.role_id == role_id)
        ).all()
        existing_ids = {item.permission_id for item in existing}
        for item in existing:
            if item.permission_id not in desired:
                session.delete(item)
        for permission_id in desired - existing_ids:
            session.add(RBACRolePermission(role_id=role_id, permission_id=permission_id))

    def _ensure_user_role(self, session: Session, user_id: int | None, role_id: int | None) -> None:
        if user_id is None or role_id is None:
            return
        existing = session.get(RBACUserRole, (user_id, role_id))
        if existing is None:
            session.add(RBACUserRole(user_id=user_id, role_id=role_id))

    def _get_user_role_codes(self, session: Session, user_id: int | None) -> list[str]:
        if user_id is None:
            return []
        statement = (
            select(RBACRole.code)
            .join(RBACUserRole, RBACUserRole.role_id == RBACRole.id)
            .where(RBACUserRole.user_id == user_id)
            .order_by(RBACRole.code)
        )
        return list(session.exec(statement).all())

    def _get_user_scopes(self, session: Session, user_id: int | None) -> list[str]:
        if user_id is None:
            return []
        statement = (
            select(RBACPermission.code)
            .join(RBACRolePermission, RBACRolePermission.permission_id == RBACPermission.id)
            .join(RBACUserRole, RBACUserRole.role_id == RBACRolePermission.role_id)
            .where(RBACUserRole.user_id == user_id)
            .order_by(RBACPermission.code)
            .distinct()
        )
        return list(session.exec(statement).all())

    def _get_role_permission_codes(self, session: Session, role_id: int | None) -> list[str]:
        if role_id is None:
            return []
        statement = (
            select(RBACPermission.code)
            .join(RBACRolePermission, RBACRolePermission.permission_id == RBACPermission.id)
            .where(RBACRolePermission.role_id == role_id)
            .order_by(RBACPermission.code)
        )
        return list(session.exec(statement).all())

    def _require_engine(self):
        if not self.available:
            raise RuntimeError(self.initialization_error or "MySQL RBAC auth is unavailable")
        return self._engine
