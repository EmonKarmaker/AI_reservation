"""SQLAlchemy models for the AI Reservation SaaS.

Phase 1.1 established the foundation (Base + mixins + enums).
Phase 1.2 adds platform-level models (users, platform_settings, audit_logs).
Phase 1.3 adds business-level models (14 tables).

Importing from this package causes all models to register on ``Base.metadata``,
which Alembic reads during autogenerate.
"""

from app.models.audit_log import AuditLog
from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin, pg_enum
from app.models.platform_setting import PlatformSetting
from app.models.user import User

__all__ = [
    "AuditLog",
    "Base",
    "PlatformSetting",
    "SoftDeleteMixin",
    "TimestampMixin",
    "User",
    "UUIDMixin",
    "pg_enum",
]
