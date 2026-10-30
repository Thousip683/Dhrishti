"""Idempotent browser session bootstrap without plaintext token storage."""
from alembic import op
import sqlalchemy as sa

revision='0002_browser_sessions'
down_revision='0001_durable_ledger'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('browser_bootstraps',
        sa.Column('nonce_hash',sa.String(64),primary_key=True),
        sa.Column('session_id',sa.String(36),sa.ForeignKey('sessions.id',ondelete='CASCADE'),nullable=False,unique=True),
        sa.Column('payload_hash',sa.String(64),nullable=False),
        sa.Column('expires_at',sa.DateTime(timezone=True),nullable=False))

def downgrade():
    op.drop_table('browser_bootstraps')
