"""create all 17 tables

Revision ID: 858813776375
Revises: 8c5d604ee81d
Create Date: 2026-04-25 01:56:02.377289

Hand-patched from autogenerate output to resolve a circular FK cycle between
``bookings`` and ``conversations`` (each references the other). Approach:

1. Create tables in a valid topological order (see below).
2. Create ``bookings`` WITHOUT its ``conversation_id`` FK — only the column.
3. Create ``conversations`` WITH its FK to ``bookings.id`` (already exists).
4. After all tables exist, add ``fk_bookings_conversation_id`` via
   ``op.create_foreign_key``.
5. ``downgrade()`` reverses: drop the deferred FK first, then tables in
   reverse dependency order.

Also fixed one autogenerate gap:
- ``ix_audit_logs_created_at_desc`` now actually uses DESC ordering via
  ``sa.literal_column('created_at DESC')`` (autogenerate dropped the DESC).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '858813776375'
down_revision: Union[str, Sequence[str], None] = '8c5d604ee81d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Topological order (each table depends only on tables above it):

      1. businesses              (no FKs)
      2. users                   (FK -> businesses)
      3. business_settings       (FK -> businesses)
      4. operating_hours         (FK -> businesses)
      5. schedule_exceptions     (FK -> businesses)
      6. customers               (FK -> businesses)
      7. services                (FK -> businesses)
      8. faqs                    (FK -> businesses)
      9. embeddings              (FK -> businesses)
     10. audit_logs              (FK -> users)
     11. platform_settings       (FK -> users)
     12. webhook_events          (no FKs)
     13. bookings                (FK -> businesses, customers, services; DEFERRED: conversations)
     14. conversations           (FK -> businesses, customers, bookings)
     15. messages                (FK -> conversations)
     16. payments                (FK -> businesses, bookings)
     17. escalations             (FK -> businesses, conversations, users)

    Deferred FK: bookings.conversation_id -> conversations.id is added at the end.
    """

    # 1. businesses
    op.create_table(
        'businesses',
        sa.Column('slug', postgresql.CITEXT(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('industry', sa.Text(), nullable=True),
        sa.Column('timezone', sa.Text(), server_default='UTC', nullable=False),
        sa.Column('currency', sa.CHAR(length=3), server_default='USD', nullable=False),
        sa.Column('phone', sa.Text(), nullable=True),
        sa.Column('email', postgresql.CITEXT(), nullable=True),
        sa.Column('website', sa.Text(), nullable=True),
        sa.Column('address', sa.Text(), nullable=True),
        sa.Column('logo_url', sa.Text(), nullable=True),
        sa.Column(
            'status',
            sa.Enum('active', 'suspended', 'pending', name='business_status'),
            server_default='active',
            nullable=False,
        ),
        sa.Column('ai_personality', sa.Text(), nullable=True),
        sa.Column('ai_greeting', sa.Text(), nullable=True),
        sa.Column('booking_window_days', sa.Integer(), server_default='60', nullable=False),
        sa.Column('cancellation_hours', sa.Integer(), server_default='24', nullable=False),
        sa.Column('stripe_account_id', sa.Text(), nullable=True),
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug'),
    )
    op.create_index('ix_businesses_deleted_at', 'businesses', ['deleted_at'], unique=False)
    op.create_index('ix_businesses_status', 'businesses', ['status'], unique=False)

    # 2. users (FK -> businesses)
    op.create_table(
        'users',
        sa.Column('email', postgresql.CITEXT(), nullable=False),
        sa.Column('password_hash', sa.Text(), nullable=False),
        sa.Column('full_name', sa.Text(), nullable=False),
        sa.Column(
            'role',
            sa.Enum('super_admin', 'business_admin', name='user_role'),
            nullable=False,
        ),
        sa.Column('business_id', sa.UUID(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(role = 'super_admin' AND business_id IS NULL) "
            "OR (role = 'business_admin' AND business_id IS NOT NULL)",
            name='ck_users_role_business_id',
        ),
        sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'),
    )
    op.create_index('ix_users_business_id', 'users', ['business_id'], unique=False)
    op.create_index('ix_users_role', 'users', ['role'], unique=False)

    # 3. business_settings
    op.create_table(
        'business_settings',
        sa.Column('business_id', sa.UUID(), nullable=False),
        sa.Column('require_payment_at_booking', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('deposit_percentage', sa.Integer(), server_default='0', nullable=False),
        sa.Column('auto_confirm_bookings', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('send_reminder_hours_before', sa.Integer(), server_default='24', nullable=False),
        sa.Column('escalation_email', postgresql.CITEXT(), nullable=True),
        sa.Column('max_daily_bookings', sa.Integer(), nullable=True),
        sa.Column('custom_api_key_encrypted', sa.Text(), nullable=True),
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('business_id'),
    )

    # 4. operating_hours
    op.create_table(
        'operating_hours',
        sa.Column('business_id', sa.UUID(), nullable=False),
        sa.Column(
            'day_of_week',
            sa.Enum('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun', name='day_of_week'),
            nullable=False,
        ),
        sa.Column('open_time', sa.Time(), nullable=False),
        sa.Column('close_time', sa.Time(), nullable=False),
        sa.Column('is_closed', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            'is_closed OR close_time > open_time',
            name='ck_operating_hours_close_after_open',
        ),
        sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'business_id', 'day_of_week', name='uq_operating_hours_business_day'
        ),
    )

    # 5. schedule_exceptions
    op.create_table(
        'schedule_exceptions',
        sa.Column('business_id', sa.UUID(), nullable=False),
        sa.Column('exception_date', sa.Date(), nullable=False),
        sa.Column('is_closed', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('open_time', sa.Time(), nullable=True),
        sa.Column('close_time', sa.Time(), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'business_id', 'exception_date', name='uq_schedule_exceptions_business_date'
        ),
    )

    # 6. customers
    op.create_table(
        'customers',
        sa.Column('business_id', sa.UUID(), nullable=False),
        sa.Column('full_name', sa.Text(), nullable=False),
        sa.Column('email', postgresql.CITEXT(), nullable=True),
        sa.Column('phone', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            'email IS NOT NULL OR phone IS NOT NULL',
            name='ck_customers_email_or_phone',
        ),
        sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_customers_business_id', 'customers', ['business_id'], unique=False)
    op.create_index(
        'ix_customers_business_id_email', 'customers', ['business_id', 'email'], unique=False
    )
    op.create_index(
        'ix_customers_business_id_phone', 'customers', ['business_id', 'phone'], unique=False
    )

    # 7. services
    op.create_table(
        'services',
        sa.Column('business_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('duration_minutes', sa.Integer(), nullable=False),
        sa.Column('buffer_minutes', sa.Integer(), server_default='0', nullable=False),
        sa.Column('price', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('display_order', sa.Integer(), server_default='0', nullable=False),
        sa.Column('image_url', sa.Text(), nullable=True),
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            'duration_minutes > 0 AND buffer_minutes >= 0 AND price >= 0',
            name='ck_services_positive_values',
        ),
        sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_services_business_id', 'services', ['business_id'], unique=False)
    op.create_index(
        'ix_services_business_id_is_active',
        'services',
        ['business_id', 'is_active'],
        unique=False,
    )
    op.create_index('ix_services_deleted_at', 'services', ['deleted_at'], unique=False)

    # 8. faqs
    op.create_table(
        'faqs',
        sa.Column('business_id', sa.UUID(), nullable=False),
        sa.Column('question', sa.Text(), nullable=False),
        sa.Column('answer', sa.Text(), nullable=False),
        sa.Column('category', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('display_order', sa.Integer(), server_default='0', nullable=False),
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_faqs_business_id', 'faqs', ['business_id'], unique=False)
    op.create_index(
        'ix_faqs_business_id_is_active', 'faqs', ['business_id', 'is_active'], unique=False
    )

    # 9. embeddings
    op.create_table(
        'embeddings',
        sa.Column('business_id', sa.UUID(), nullable=False),
        sa.Column(
            'source_type',
            sa.Enum('business', 'service', 'faq', name='embedding_source_type'),
            nullable=False,
        ),
        sa.Column('source_id', sa.UUID(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('embedding', Vector(384), nullable=False),
        sa.Column(
            'metadata',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source_type', 'source_id', name='uq_embeddings_source'),
    )
    op.create_index('ix_embeddings_business_id', 'embeddings', ['business_id'], unique=False)
    op.create_index(
        'ix_embeddings_hnsw',
        'embeddings',
        ['embedding'],
        unique=False,
        postgresql_using='hnsw',
        postgresql_ops={'embedding': 'vector_cosine_ops'},
    )

    # 10. audit_logs
    op.create_table(
        'audit_logs',
        sa.Column('actor_user_id', sa.UUID(), nullable=False),
        sa.Column('action', sa.Text(), nullable=False),
        sa.Column('entity_type', sa.Text(), nullable=False),
        sa.Column('entity_id', sa.UUID(), nullable=True),
        sa.Column(
            'metadata',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column('ip_address', postgresql.INET(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_audit_logs_actor_user_id', 'audit_logs', ['actor_user_id'], unique=False
    )
    # DESC ordering preserved manually (autogenerate dropped it).
    op.create_index(
        'ix_audit_logs_created_at_desc',
        'audit_logs',
        [sa.literal_column('created_at DESC')],
        unique=False,
    )
    op.create_index(
        'ix_audit_logs_entity_type_entity_id',
        'audit_logs',
        ['entity_type', 'entity_id'],
        unique=False,
    )

    # 11. platform_settings (FK -> users)
    op.create_table(
        'platform_settings',
        sa.Column('key', sa.Text(), nullable=False),
        sa.Column('value_encrypted', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('updated_by', sa.UUID(), nullable=True),
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key'),
    )

    # 12. webhook_events (no FKs)
    op.create_table(
        'webhook_events',
        sa.Column('source', sa.Text(), nullable=False),
        sa.Column('event_id', sa.Text(), nullable=False),
        sa.Column('event_type', sa.Text(), nullable=False),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('processed', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source', 'event_id', name='uq_webhook_events_source_event'),
    )
    op.create_index(
        'ix_webhook_events_processed_created_at',
        'webhook_events',
        ['processed', 'created_at'],
        unique=False,
    )

    # 13. bookings — created WITHOUT the conversation_id FK (added at the end).
    #    The column exists, only the FK constraint is deferred.
    op.create_table(
        'bookings',
        sa.Column('business_id', sa.UUID(), nullable=False),
        sa.Column('customer_id', sa.UUID(), nullable=False),
        sa.Column('service_id', sa.UUID(), nullable=False),
        sa.Column('conversation_id', sa.UUID(), nullable=True),
        sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ends_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            'status',
            sa.Enum(
                'pending_payment', 'confirmed', 'cancelled', 'completed', 'no_show',
                name='booking_status',
            ),
            server_default='pending_payment',
            nullable=False,
        ),
        sa.Column('total_amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('currency', sa.CHAR(length=3), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('admin_notes', sa.Text(), nullable=True),
        sa.Column('idempotency_key', sa.Text(), nullable=False),
        sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancelled_reason', sa.Text(), nullable=True),
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint('ends_at > starts_at', name='ck_bookings_ends_after_starts'),
        sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['service_id'], ['services.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('idempotency_key'),
    )
    op.create_index('ix_bookings_business_id', 'bookings', ['business_id'], unique=False)
    op.create_index(
        'ix_bookings_business_id_starts_at',
        'bookings',
        ['business_id', 'starts_at'],
        unique=False,
    )
    op.create_index('ix_bookings_customer_id', 'bookings', ['customer_id'], unique=False)
    op.create_index('ix_bookings_service_id', 'bookings', ['service_id'], unique=False)
    op.create_index('ix_bookings_status', 'bookings', ['status'], unique=False)

    # 14. conversations (FK -> bookings works — bookings now exists)
    op.create_table(
        'conversations',
        sa.Column('business_id', sa.UUID(), nullable=False),
        sa.Column('customer_id', sa.UUID(), nullable=True),
        sa.Column(
            'channel',
            sa.Enum('chat', 'voice', name='conversation_channel'),
            nullable=False,
        ),
        sa.Column(
            'status',
            sa.Enum('active', 'completed', 'abandoned', 'escalated', name='conversation_status'),
            server_default='active',
            nullable=False,
        ),
        sa.Column('session_token', sa.Text(), nullable=False),
        sa.Column('vapi_call_id', sa.Text(), nullable=True),
        sa.Column(
            'langgraph_state',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            'intent_history',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column('booking_id', sa.UUID(), nullable=True),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['booking_id'], ['bookings.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('session_token'),
        sa.UniqueConstraint('vapi_call_id'),
    )
    op.create_index(
        'ix_conversations_business_id', 'conversations', ['business_id'], unique=False
    )
    op.create_index(
        'ix_conversations_business_id_created_at',
        'conversations',
        ['business_id', sa.literal_column('created_at DESC')],
        unique=False,
    )
    op.create_index(
        'ix_conversations_status', 'conversations', ['status'], unique=False
    )

    # 15. messages (FK -> conversations)
    op.create_table(
        'messages',
        sa.Column('conversation_id', sa.UUID(), nullable=False),
        sa.Column(
            'role',
            sa.Enum('user', 'assistant', 'system', 'tool', name='message_role'),
            nullable=False,
        ),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column(
            'metadata',
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column('tokens_used', sa.Integer(), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_messages_conversation_id', 'messages', ['conversation_id'], unique=False
    )
    op.create_index(
        'ix_messages_conversation_id_created_at',
        'messages',
        ['conversation_id', 'created_at'],
        unique=False,
    )

    # 16. payments (FK -> businesses, bookings)
    op.create_table(
        'payments',
        sa.Column('business_id', sa.UUID(), nullable=False),
        sa.Column('booking_id', sa.UUID(), nullable=False),
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('currency', sa.CHAR(length=3), nullable=False),
        sa.Column(
            'status',
            sa.Enum('pending', 'succeeded', 'failed', 'refunded', name='payment_status'),
            server_default='pending',
            nullable=False,
        ),
        sa.Column('stripe_checkout_session_id', sa.Text(), nullable=True),
        sa.Column('stripe_payment_intent_id', sa.Text(), nullable=True),
        sa.Column('stripe_refund_id', sa.Text(), nullable=True),
        sa.Column('failure_reason', sa.Text(), nullable=True),
        sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('refunded_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['booking_id'], ['bookings.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('stripe_checkout_session_id'),
        sa.UniqueConstraint('stripe_payment_intent_id'),
    )
    op.create_index('ix_payments_booking_id', 'payments', ['booking_id'], unique=False)
    op.create_index('ix_payments_business_id', 'payments', ['business_id'], unique=False)
    op.create_index('ix_payments_status', 'payments', ['status'], unique=False)

    # 17. escalations (FK -> businesses, conversations, users)
    op.create_table(
        'escalations',
        sa.Column('business_id', sa.UUID(), nullable=False),
        sa.Column('conversation_id', sa.UUID(), nullable=False),
        sa.Column('customer_name', sa.Text(), nullable=True),
        sa.Column('customer_phone', sa.Text(), nullable=True),
        sa.Column('customer_email', postgresql.CITEXT(), nullable=True),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column(
            'priority',
            sa.Enum('low', 'medium', 'high', name='escalation_priority'),
            server_default='medium',
            nullable=False,
        ),
        sa.Column(
            'status',
            sa.Enum('open', 'in_progress', 'resolved', 'dismissed', name='escalation_status'),
            server_default='open',
            nullable=False,
        ),
        sa.Column('transcript_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('suggested_response', sa.Text(), nullable=True),
        sa.Column('admin_notes', sa.Text(), nullable=True),
        sa.Column('resolved_by', sa.UUID(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('email_sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['business_id'], ['businesses.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['resolved_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_escalations_business_id', 'escalations', ['business_id'], unique=False)
    op.create_index(
        'ix_escalations_business_id_status',
        'escalations',
        ['business_id', 'status'],
        unique=False,
    )
    op.create_index(
        'ix_escalations_conversation_id', 'escalations', ['conversation_id'], unique=False
    )
    op.create_index(
        'ix_escalations_priority_created_at',
        'escalations',
        ['priority', sa.literal_column('created_at DESC')],
        unique=False,
    )

    # Deferred FK: bookings.conversation_id -> conversations.id
    # Added after both tables exist to resolve the circular dependency.
    op.create_foreign_key(
        'fk_bookings_conversation_id',
        'bookings',
        'conversations',
        ['conversation_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    """Downgrade schema.

    Reverse of upgrade: drop the deferred FK first, then tables in reverse
    dependency order.
    """
    # Drop the deferred FK first so bookings/conversations can be dropped in any order.
    op.drop_constraint('fk_bookings_conversation_id', 'bookings', type_='foreignkey')

    # 17. escalations
    op.drop_index('ix_escalations_priority_created_at', table_name='escalations')
    op.drop_index('ix_escalations_conversation_id', table_name='escalations')
    op.drop_index('ix_escalations_business_id_status', table_name='escalations')
    op.drop_index('ix_escalations_business_id', table_name='escalations')
    op.drop_table('escalations')

    # 16. payments
    op.drop_index('ix_payments_status', table_name='payments')
    op.drop_index('ix_payments_business_id', table_name='payments')
    op.drop_index('ix_payments_booking_id', table_name='payments')
    op.drop_table('payments')

    # 15. messages
    op.drop_index('ix_messages_conversation_id_created_at', table_name='messages')
    op.drop_index('ix_messages_conversation_id', table_name='messages')
    op.drop_table('messages')

    # 14. conversations
    op.drop_index('ix_conversations_status', table_name='conversations')
    op.drop_index('ix_conversations_business_id_created_at', table_name='conversations')
    op.drop_index('ix_conversations_business_id', table_name='conversations')
    op.drop_table('conversations')

    # 13. bookings
    op.drop_index('ix_bookings_status', table_name='bookings')
    op.drop_index('ix_bookings_service_id', table_name='bookings')
    op.drop_index('ix_bookings_customer_id', table_name='bookings')
    op.drop_index('ix_bookings_business_id_starts_at', table_name='bookings')
    op.drop_index('ix_bookings_business_id', table_name='bookings')
    op.drop_table('bookings')

    # 12. webhook_events
    op.drop_index('ix_webhook_events_processed_created_at', table_name='webhook_events')
    op.drop_table('webhook_events')

    # 11. platform_settings
    op.drop_table('platform_settings')

    # 10. audit_logs
    op.drop_index('ix_audit_logs_entity_type_entity_id', table_name='audit_logs')
    op.drop_index('ix_audit_logs_created_at_desc', table_name='audit_logs')
    op.drop_index('ix_audit_logs_actor_user_id', table_name='audit_logs')
    op.drop_table('audit_logs')

    # 9. embeddings
    op.drop_index(
        'ix_embeddings_hnsw',
        table_name='embeddings',
        postgresql_using='hnsw',
        postgresql_ops={'embedding': 'vector_cosine_ops'},
    )
    op.drop_index('ix_embeddings_business_id', table_name='embeddings')
    op.drop_table('embeddings')

    # 8. faqs
    op.drop_index('ix_faqs_business_id_is_active', table_name='faqs')
    op.drop_index('ix_faqs_business_id', table_name='faqs')
    op.drop_table('faqs')

    # 7. services
    op.drop_index('ix_services_deleted_at', table_name='services')
    op.drop_index('ix_services_business_id_is_active', table_name='services')
    op.drop_index('ix_services_business_id', table_name='services')
    op.drop_table('services')

    # 6. customers
    op.drop_index('ix_customers_business_id_phone', table_name='customers')
    op.drop_index('ix_customers_business_id_email', table_name='customers')
    op.drop_index('ix_customers_business_id', table_name='customers')
    op.drop_table('customers')

    # 5. schedule_exceptions
    op.drop_table('schedule_exceptions')

    # 4. operating_hours
    op.drop_table('operating_hours')

    # 3. business_settings
    op.drop_table('business_settings')

    # 2. users
    op.drop_index('ix_users_role', table_name='users')
    op.drop_index('ix_users_business_id', table_name='users')
    op.drop_table('users')

    # 1. businesses
    op.drop_index('ix_businesses_status', table_name='businesses')
    op.drop_index('ix_businesses_deleted_at', table_name='businesses')
    op.drop_table('businesses')
