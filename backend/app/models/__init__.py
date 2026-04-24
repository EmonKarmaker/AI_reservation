"""SQLAlchemy models for the AI Reservation SaaS.

Phase 1.1 established the foundation (Base + mixins + enums).
Phase 1.2 added platform-level models (users, platform_settings, audit_logs).
Phase 1.3a adds the tenant foundation (businesses, business_settings,
operating_hours, schedule_exceptions).
Phase 1.3b will add Service, Customer, Booking, Payment.
Phase 1.3c will add Conversation, Message, Escalation, Faq, Embedding,
WebhookEvent, plus wire up all SQLAlchemy relationships.

Importing from this package causes all models to register on ``Base.metadata``,
which Alembic reads during autogenerate.
"""

from app.models.audit_log import AuditLog
from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin, pg_enum
from app.models.business import Business
from app.models.business_setting import BusinessSetting
from app.models.operating_hours import OperatingHours
from app.models.platform_setting import PlatformSetting
from app.models.schedule_exception import ScheduleException
from app.models.user import User

__all__ = [
    "AuditLog",
    "Base",
    "Business",
    "BusinessSetting",
    "OperatingHours",
    "PlatformSetting",
    "ScheduleException",
    "SoftDeleteMixin",
    "TimestampMixin",
    "User",
    "UUIDMixin",
    "pg_enum",
]
