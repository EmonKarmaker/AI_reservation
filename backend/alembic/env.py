"""Alembic environment script.

Hooks wired up here:

1. ``target_metadata = Base.metadata`` — enables ``--autogenerate`` by exposing
   the schema of all 17 models. Importing ``app.models`` triggers loading of
   every model file via ``__init__.py`` so they all register on ``Base.metadata``.

2. ``render_item`` — teaches Alembic how to render pgvector ``Vector(n)`` columns
   in generated migrations. Without this, autogenerate either omits the column
   or writes an unusable type.

3. ``include_object`` — prevents autogenerate from trying to re-create the 11
   Postgres enum types already created by migration
   ``8c5d604ee81d_extensions_and_enums``. SQLAlchemy sees the enum types as part
   of the schema; without this filter it emits duplicate ``CREATE TYPE`` calls.

The list of pre-existing enum names below must stay in sync with the enums
declared in ``app/models/enums.py``.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from pgvector.sqlalchemy import Vector
from sqlalchemy import engine_from_config, pool

from app.config import settings
from app.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override sqlalchemy.url from settings so no secret lives in alembic.ini.
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL_SYNC)

# Enables ``alembic revision --autogenerate`` by comparing Base.metadata
# against the live database schema.
target_metadata = Base.metadata

# Enum types created by the bootstrap migration ``8c5d604ee81d``.
# Alembic must not re-create these when generating autogenerate migrations.
_PREEXISTING_ENUMS: frozenset[str] = frozenset(
    {
        "booking_status",
        "business_status",
        "conversation_channel",
        "conversation_status",
        "day_of_week",
        "embedding_source_type",
        "escalation_priority",
        "escalation_status",
        "message_role",
        "payment_status",
        "user_role",
    }
)


def _include_object(
    object_: object,
    name: str | None,
    type_: str,
    reflected: bool,  # noqa: ARG001 - alembic API
    compare_to: object,  # noqa: ARG001 - alembic API
) -> bool:
    """Filter which objects Alembic considers during autogenerate.

    Skip the 11 pre-existing enum types so Alembic does not try to re-create them.
    """
    if type_ == "type" and name in _PREEXISTING_ENUMS:
        return False
    return True


def _render_item(type_: str, obj: object, autogen_context: object) -> str | bool:
    """Custom rendering for Alembic autogenerate.

    Emit a correct ``pgvector.sqlalchemy.Vector(n)`` reference and ensure the
    import is added to the migration file. Return ``False`` for everything else
    so Alembic falls back to its default rendering.
    """
    if type_ == "type" and isinstance(obj, Vector):
        autogen_context.imports.add("from pgvector.sqlalchemy import Vector")  # type: ignore[attr-defined]
        return f"Vector({obj.dim})"
    return False


def run_migrations_offline() -> None:
    """Run migrations without a live DB connection (generates SQL to stdout)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=_include_object,
        render_item=_render_item,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live DB connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=_include_object,
            render_item=_render_item,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
