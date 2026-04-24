"""Python enums mirroring the Postgres enum types.

The Postgres enums were created by migration ``8c5d604ee81d_extensions_and_enums``.
String values here must match Postgres enum labels exactly (case-sensitive).

When a model column uses one of these, bind it with
``SQLAlchemy.Enum(MyEnum, name="postgres_enum_name", create_type=False)`` —
``create_type=False`` because the migration already created the types.
"""

from __future__ import annotations

from enum import Enum


class UserRole(str, Enum):
    """Postgres enum ``user_role``."""

    SUPER_ADMIN = "super_admin"
    BUSINESS_ADMIN = "business_admin"


class BusinessStatus(str, Enum):
    """Postgres enum ``business_status``."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    PENDING = "pending"


class BookingStatus(str, Enum):
    """Postgres enum ``booking_status``."""

    PENDING_PAYMENT = "pending_payment"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    NO_SHOW = "no_show"


class PaymentStatus(str, Enum):
    """Postgres enum ``payment_status``."""

    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUNDED = "refunded"


class ConversationChannel(str, Enum):
    """Postgres enum ``conversation_channel``."""

    CHAT = "chat"
    VOICE = "voice"


class ConversationStatus(str, Enum):
    """Postgres enum ``conversation_status``."""

    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"
    ESCALATED = "escalated"


class MessageRole(str, Enum):
    """Postgres enum ``message_role``."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class EscalationStatus(str, Enum):
    """Postgres enum ``escalation_status``."""

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class EscalationPriority(str, Enum):
    """Postgres enum ``escalation_priority``."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class EmbeddingSourceType(str, Enum):
    """Postgres enum ``embedding_source_type``."""

    BUSINESS = "business"
    SERVICE = "service"
    FAQ = "faq"


class DayOfWeek(str, Enum):
    """Postgres enum ``day_of_week``."""

    MON = "mon"
    TUE = "tue"
    WED = "wed"
    THU = "thu"
    FRI = "fri"
    SAT = "sat"
    SUN = "sun"
