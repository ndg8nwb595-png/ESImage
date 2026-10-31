"""用户、角色、权限相关 ORM 模型。

字段与约束对齐 docs/prd/10-数据模型与存储prd.md §4.1~§4.5。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

# 用户-角色关联（无独立模型）
user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True),
    Column("role_id", BigInteger, ForeignKey("roles.id", ondelete="RESTRICT"), primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)
Index("idx_user_roles_role_id", user_roles.c.role_id)

# 角色-权限关联（无独立模型）
role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", BigInteger, ForeignKey("roles.id", ondelete="RESTRICT"), primary_key=True),
    Column(
        "permission_id",
        BigInteger,
        ForeignKey("permissions.id", ondelete="RESTRICT"),
        primary_key=True,
    ),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)


class User(Base):
    """用户表 users。"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(20), nullable=False)
    display_name: Mapped[str] = mapped_column(String(30), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    avatar_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'active'"))
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    roles: Mapped[list["Role"]] = relationship(
        secondary=user_roles, lazy="selectin", order_by="Role.code", back_populates="users"
    )

    __table_args__ = (
        UniqueConstraint("username", name="uq_users_username"),
        CheckConstraint(r"username ~ '^[A-Za-z0-9_]{4,20}$'", name="ck_users_username_format"),
        CheckConstraint("status IN ('active','disabled','deleted')", name="ck_users_status"),
        Index("idx_users_status", "status"),
        Index("idx_users_created_at", "created_at"),
    )


class Role(Base):
    """角色表 roles。"""

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    permissions: Mapped[list["Permission"]] = relationship(
        secondary=role_permissions,
        lazy="selectin",
        order_by="Permission.code",
        back_populates="roles",
    )
    users: Mapped[list[User]] = relationship(secondary=user_roles, back_populates="roles")

    __table_args__ = (
        UniqueConstraint("code", name="uq_roles_code"),
        CheckConstraint("code IN ('user','admin','super_admin')", name="ck_roles_code"),
    )


class Permission(Base):
    """权限点表 permissions。"""

    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    group_name: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_super_only: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    roles: Mapped[list[Role]] = relationship(
        secondary=role_permissions, back_populates="permissions"
    )

    __table_args__ = (
        UniqueConstraint("code", name="uq_permissions_code"),
        CheckConstraint("type IN ('menu','action')", name="ck_permissions_type"),
    )
