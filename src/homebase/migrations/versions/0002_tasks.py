"""Tasks"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("id", sa.Integer, sa.Identity(), primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("notes", sa.Text),
        sa.Column("room", sa.Text),
        sa.Column("estimated_minutes", sa.Integer),
        sa.Column("interval_days", sa.Integer),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_done_at", sa.DateTime(timezone=True)),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("estimated_minutes > 0", name="estimated_minutes_positive"),
        sa.CheckConstraint("interval_days > 0", name="interval_days_positive"),
    )


def downgrade() -> None:
    op.drop_table("tasks")
