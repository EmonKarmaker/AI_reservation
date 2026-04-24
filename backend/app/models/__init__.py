"""SQLAlchemy models for the AI Reservation SaaS.

Phase 1.1: Base + mixins + enums.
Phase 1.2: platform-level models (users, platform_settings, audit_logs).
Phase 1.3a: tenant foundation (businesses, business_settings, operating_hours,
   schedule_exceptions).
Phase 1.3b: booking core (services, customers, bookings, payments).
Phase 1.3c: AI + infra (conversations, messages, escalations, faqs, embeddings,
   webhook_events).
Phase 1.3d (next): wire SQLAlchemy relationships across all models.

Importing from this package causes all models to register on ``Base.metadata``,
which Alembic reads during autogenerate.
"""

from app.models.audit_log import AuditLog
from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin, pg_enum
from app.models.booking import Booking
from app.models.business import Business
from app.models.business_setting import BusinessSetting
from app.models.conversation import Conversation
from app.models.customer import Customer
from app.models.embedding import Embedding
from app.models.escalation import Escalation
from app.models.faq import Faq
from app.models.message import Message
from app.models.operating_hours import OperatingHours
from app.models.payment import Payment
from app.models.platform_setting import PlatformSetting
from app.models.schedule_exception import ScheduleException
from app.models.service import Service
from app.models.user import User
from app.models.webhook_event import WebhookEvent

__all__ = [
    "AuditLog",
    "Base",
    "Booking",
    "Business",
    "BusinessSetting",
    "Conversation",
    "Customer",
    "Embedding",
    "Escalation",
    "Faq",
    "Message",
    "OperatingHours",
    "Payment",
    "PlatformSetting",
    "ScheduleException",
    "Service",
    "SoftDeleteMixin",
    "TimestampMixin",
    "User",
    "UUIDMixin",
    "WebhookEvent",
    "pg_enum",
]
