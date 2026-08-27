"""Initial schema: patients, appointments, sessions, messages.

Revision ID: 0001
Revises:
Create Date: 2026-08-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Enum types are created explicitly (create_type=False on the columns) so the
# downgrade can drop them deterministically.
patient_status = postgresql.ENUM(
    "stable", "admitted", "critical", "discharged", name="patient_status", create_type=False
)
appointment_status = postgresql.ENUM(
    "scheduled", "completed", "cancelled", "no_show", name="appointment_status", create_type=False
)
message_role = postgresql.ENUM(
    "user", "assistant", "system", name="message_role", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()

    # Extensions first. pgvector is reserved for the RAG phase; no vector columns
    # exist yet because no consumer does.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    patient_status.create(bind, checkfirst=True)
    appointment_status.create(bind, checkfirst=True)
    message_role.create(bind, checkfirst=True)

    # Human-readable MRNs (e.g. P-10023) are allocated from this sequence.
    op.execute("CREATE SEQUENCE IF NOT EXISTS patient_mrn_seq START WITH 10023")

    op.create_table(
        "patients",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "mrn",
            sa.Text(),
            server_default=sa.text("'P-' || nextval('patient_mrn_seq')"),
            nullable=False,
        ),
        sa.Column("phone", sa.Text(), nullable=False),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column("status", patient_status, server_default=sa.text("'stable'"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_patients"),
        sa.UniqueConstraint("mrn", name="uq_patients_mrn"),
        sa.UniqueConstraint("phone", name="uq_patients_phone"),
    )

    op.create_table(
        "appointments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("department", sa.Text(), nullable=False),
        sa.Column(
            "status",
            appointment_status,
            server_default=sa.text("'scheduled'"),
            nullable=False,
        ),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_appointments"),
        sa.ForeignKeyConstraint(
            ["patient_id"],
            ["patients.id"],
            name="fk_appointments_patient_id_patients",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_appointments_patient_id_scheduled_for",
        "appointments",
        ["patient_id", "scheduled_for"],
    )

    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sessions"),
        sa.ForeignKeyConstraint(
            ["patient_id"],
            ["patients.id"],
            name="fk_sessions_patient_id_patients",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_sessions_patient_id", "sessions", ["patient_id"])
    op.create_index("ix_sessions_created_at", "sessions", ["created_at"])

    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", message_role, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_messages"),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name="fk_messages_session_id_sessions",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_messages_session_id_created_at", "messages", ["session_id", "created_at"])


def downgrade() -> None:
    bind = op.get_bind()

    op.drop_index("ix_messages_session_id_created_at", table_name="messages")
    op.drop_table("messages")

    op.drop_index("ix_sessions_created_at", table_name="sessions")
    op.drop_index("ix_sessions_patient_id", table_name="sessions")
    op.drop_table("sessions")

    op.drop_index("ix_appointments_patient_id_scheduled_for", table_name="appointments")
    op.drop_table("appointments")

    op.drop_table("patients")

    op.execute("DROP SEQUENCE IF EXISTS patient_mrn_seq")

    message_role.drop(bind, checkfirst=True)
    appointment_status.drop(bind, checkfirst=True)
    patient_status.drop(bind, checkfirst=True)

    op.execute("DROP EXTENSION IF EXISTS vector")
