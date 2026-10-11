"""Persist exclusive ownership of source videos by a batch."""

from alembic import op
import sqlalchemy as sa


revision = "0003_video_batch_ownership"
down_revision = "0002_sequence_batches"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("assets", sa.Column("video_batch_name", sa.String(200), nullable=True))
    op.create_index("ix_assets_video_batch_name", "assets", ["video_batch_name"])


def downgrade() -> None:
    op.drop_index("ix_assets_video_batch_name", table_name="assets")
    op.drop_column("assets", "video_batch_name")
