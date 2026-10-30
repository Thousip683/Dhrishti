"""Normalized application data; independent of ADK session implementation."""
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import JSON, Boolean, CheckConstraint, Date, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class SessionRow(Base):
    __tablename__ = 'sessions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    context: Mapped[dict] = mapped_column(JSON)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)

class CalculationRow(Base):
    __tablename__ = 'calculations'
    __table_args__ = (UniqueConstraint('session_id', 'id', name='uq_calculation_owner'),
        CheckConstraint("lifecycle IN ('uncommitted', 'active', 'superseded', 'deleted')", name='ck_calculation_lifecycle'),
        CheckConstraint('kg_co2e >= 0', name='ck_calculation_nonnegative'))
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey('sessions.id', ondelete='CASCADE'), index=True)
    kg_co2e: Mapped[Decimal] = mapped_column(Numeric(20,6))
    lifecycle: Mapped[str] = mapped_column(String(20), default='uncommitted')
    receipt: Mapped[dict] = mapped_column(JSON)

class ActivityRow(Base):
    __tablename__ = 'activities'
    __table_args__ = (ForeignKeyConstraint(['session_id','calculation_id'], ['calculations.session_id','calculations.id'], ondelete='CASCADE', name='fk_activity_calculation_owner'),
        UniqueConstraint('calculation_id', name='uq_activity_calculation'),
        CheckConstraint('revision > 0', name='ck_activity_revision'),
        CheckConstraint('kg_co2e >= 0', name='ck_activity_nonnegative'),
        Index('ix_activity_owner_date', 'session_id', 'activity_date', 'created_at', 'id'))
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey('sessions.id', ondelete='CASCADE'))
    calculation_id: Mapped[str] = mapped_column(String(36))
    category: Mapped[str] = mapped_column(String(20))
    activity_date: Mapped[date] = mapped_column(Date)
    kg_co2e: Mapped[Decimal] = mapped_column(Numeric(20,6))
    note: Mapped[str] = mapped_column(String(500))
    revision: Mapped[int] = mapped_column(Integer)
    deleted: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class IdempotencyRow(Base):
    __tablename__ = 'idempotency_records'
    session_id: Mapped[str] = mapped_column(ForeignKey('sessions.id', ondelete='CASCADE'), primary_key=True)
    key: Mapped[str] = mapped_column(String(512), primary_key=True)
    payload_hash: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class RequestRow(Base):
    __tablename__ = 'requests'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey('sessions.id', ondelete='CASCADE'), index=True)
    status: Mapped[str] = mapped_column(String(32))
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class CorrectionRow(Base):
    __tablename__ = 'activity_corrections'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey('sessions.id', ondelete='CASCADE'), index=True)
    activity_id: Mapped[str] = mapped_column(ForeignKey('activities.id', ondelete='CASCADE'))
    previous_calculation_id: Mapped[str] = mapped_column(String(36))
    replacement_calculation_id: Mapped[str] = mapped_column(String(36))
    revision: Mapped[int] = mapped_column(Integer)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class BrowserBootstrapRow(Base):
    __tablename__ = 'browser_bootstraps'
    nonce_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey('sessions.id', ondelete='CASCADE'), unique=True)
    payload_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
