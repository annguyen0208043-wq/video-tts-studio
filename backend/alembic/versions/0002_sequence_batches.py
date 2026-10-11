"""Add independent sequence batch names."""

from alembic import op
import sqlalchemy as sa


revision = "0002_sequence_batches"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sequences", sa.Column("batch_name", sa.String(200), nullable=True))
    op.execute("UPDATE sequences SET batch_name = 'Batch 1' WHERE batch_name IS NULL")
    op.alter_column("sequences", "batch_name", nullable=False)
    op.create_index("ix_sequences_batch_name", "sequences", ["batch_name"])


def downgrade() -> None:
    op.drop_index("ix_sequences_batch_name", table_name="sequences")
    op.drop_column("sequences", "batch_name")
