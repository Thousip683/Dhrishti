"""Initial durable application ledger."""
from alembic import op
import sqlalchemy as sa

revision='0001_durable_ledger'
down_revision=None
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('sessions',sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('token_hash',sa.String(64),nullable=False,unique=True),sa.Column('context',sa.JSON(),nullable=False),
        sa.Column('expires_at',sa.DateTime(timezone=True),nullable=False),sa.Column('revision',sa.Integer(),nullable=False))
    op.create_index('ix_sessions_expires_at','sessions',['expires_at'])
    op.create_table('calculations',sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('session_id',sa.String(36),sa.ForeignKey('sessions.id',ondelete='CASCADE'),nullable=False),
        sa.Column('kg_co2e',sa.Numeric(20,6),nullable=False),sa.Column('lifecycle',sa.String(20),nullable=False),
        sa.Column('receipt',sa.JSON(),nullable=False),sa.UniqueConstraint('session_id','id',name='uq_calculation_owner'),
        sa.CheckConstraint("lifecycle IN ('uncommitted', 'active', 'superseded', 'deleted')",name='ck_calculation_lifecycle'),
        sa.CheckConstraint('kg_co2e >= 0',name='ck_calculation_nonnegative'))
    op.create_index('ix_calculations_session_id','calculations',['session_id'])
    op.create_table('activities',sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('session_id',sa.String(36),sa.ForeignKey('sessions.id',ondelete='CASCADE'),nullable=False),
        sa.Column('calculation_id',sa.String(36),nullable=False),sa.Column('category',sa.String(20),nullable=False),
        sa.Column('activity_date',sa.Date(),nullable=False),sa.Column('kg_co2e',sa.Numeric(20,6),nullable=False),
        sa.Column('note',sa.String(500),nullable=False),sa.Column('revision',sa.Integer(),nullable=False),
        sa.Column('deleted',sa.Boolean(),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.ForeignKeyConstraint(['session_id','calculation_id'],['calculations.session_id','calculations.id'],ondelete='CASCADE',name='fk_activity_calculation_owner'),
        sa.UniqueConstraint('calculation_id',name='uq_activity_calculation'),
        sa.CheckConstraint('revision > 0',name='ck_activity_revision'),sa.CheckConstraint('kg_co2e >= 0',name='ck_activity_nonnegative'))
    op.create_index('ix_activity_owner_date','activities',['session_id','activity_date','created_at','id'])
    op.create_table('idempotency_records',sa.Column('session_id',sa.String(36),sa.ForeignKey('sessions.id',ondelete='CASCADE'),primary_key=True),
        sa.Column('key',sa.String(512),primary_key=True),sa.Column('payload_hash',sa.String(64),nullable=False),
        sa.Column('response',sa.JSON(),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_table('requests',sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('session_id',sa.String(36),sa.ForeignKey('sessions.id',ondelete='CASCADE'),nullable=False),
        sa.Column('status',sa.String(32),nullable=False),sa.Column('result',sa.JSON(),nullable=True),sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_requests_session_id','requests',['session_id'])
    op.create_table('activity_corrections',sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('session_id',sa.String(36),sa.ForeignKey('sessions.id',ondelete='CASCADE'),nullable=False),
        sa.Column('activity_id',sa.String(36),sa.ForeignKey('activities.id',ondelete='CASCADE'),nullable=False),
        sa.Column('previous_calculation_id',sa.String(36),nullable=False),sa.Column('replacement_calculation_id',sa.String(36),nullable=False),
        sa.Column('revision',sa.Integer(),nullable=False),sa.Column('changed_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_activity_corrections_session_id','activity_corrections',['session_id'])

def downgrade():
    for name in ['activity_corrections','requests','idempotency_records','activities','calculations','sessions']:
        op.drop_table(name)
