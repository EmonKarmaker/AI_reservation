"""extensions_and_enums

Revision ID: 8c5d604ee81d
Revises:
Create Date: 2026-04-22 12:45:00.230304

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '8c5d604ee81d'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Extensions
    # pgcrypto  → gen_random_uuid() for UUID PKs
    # citext    → case-insensitive text for emails
    # vector    → pgvector for embedding similarity search (384 dims)
    # ------------------------------------------------------------------
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ------------------------------------------------------------------
    # Enums (must exist before any table that references them)
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TYPE user_role AS ENUM ('super_admin', 'business_admin')
    """)

    op.execute("""
        CREATE TYPE business_status AS ENUM ('active', 'suspended', 'pending')
    """)

    op.execute("""
        CREATE TYPE booking_status AS ENUM (
            'pending_payment', 'confirmed', 'cancelled', 'completed', 'no_show'
        )
    """)

    op.execute("""
        CREATE TYPE payment_status AS ENUM (
            'pending', 'succeeded', 'failed', 'refunded'
        )
    """)

    op.execute("""
        CREATE TYPE conversation_channel AS ENUM ('chat', 'voice')
    """)

    op.execute("""
        CREATE TYPE conversation_status AS ENUM (
            'active', 'completed', 'abandoned', 'escalated'
        )
    """)

    op.execute("""
        CREATE TYPE message_role AS ENUM ('user', 'assistant', 'system', 'tool')
    """)

    op.execute("""
        CREATE TYPE escalation_status AS ENUM (
            'open', 'in_progress', 'resolved', 'dismissed'
        )
    """)

    op.execute("""
        CREATE TYPE escalation_priority AS ENUM ('low', 'medium', 'high')
    """)

    op.execute("""
        CREATE TYPE embedding_source_type AS ENUM ('business', 'service', 'faq')
    """)

    op.execute("""
        CREATE TYPE day_of_week AS ENUM (
            'mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'
        )
    """)


def downgrade() -> None:
    # Drop enums in reverse creation order.
    # Extensions are NOT dropped — other Supabase internals may depend on them.
    op.execute("DROP TYPE IF EXISTS day_of_week")
    op.execute("DROP TYPE IF EXISTS embedding_source_type")
    op.execute("DROP TYPE IF EXISTS escalation_priority")
    op.execute("DROP TYPE IF EXISTS escalation_status")
    op.execute("DROP TYPE IF EXISTS message_role")
    op.execute("DROP TYPE IF EXISTS conversation_status")
    op.execute("DROP TYPE IF EXISTS conversation_channel")
    op.execute("DROP TYPE IF EXISTS payment_status")
    op.execute("DROP TYPE IF EXISTS booking_status")
    op.execute("DROP TYPE IF EXISTS business_status")
    op.execute("DROP TYPE IF EXISTS user_role")
