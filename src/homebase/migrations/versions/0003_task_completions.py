"""Task completions"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "task_completions",
        sa.Column("id", sa.Integer, sa.Identity(), primary_key=True),
        sa.Column(
            "task_id",
            sa.Integer,
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("actual_minutes", sa.Integer),
        sa.CheckConstraint("actual_minutes > 0", name="actual_minutes_positive"),
    )


def downgrade() -> None:
    op.drop_table("task_completions")
