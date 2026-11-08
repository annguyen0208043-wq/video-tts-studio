"""Persist voice definitions and listening samples in the shared database."""

from alembic import op
import sqlalchemy as sa

revision = "0004_voice_library"
down_revision = "0003_video_batch_ownership"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "voice_library",
        sa.Column("id", sa.String(200), primary_key=True),
        sa.Column("label", sa.String(500), nullable=False),
        sa.Column("custom", sa.Boolean(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("reference_audio", sa.LargeBinary(), nullable=True),
        sa.Column("preview_key", sa.String(64), unique=True, nullable=True),
        sa.Column("preview_audio", sa.LargeBinary(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    if op.get_bind().dialect.name == "postgresql":
        # The backend connects as table owner; public Supabase API roles must
        # not read speaker embeddings or reference audio directly.
        op.execute("ALTER TABLE voice_library ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_table("voice_library")
