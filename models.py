"""Database models for RainMaker"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, Integer, DateTime, Float, ForeignKey, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from config import get_settings

Base = declarative_base()


class User(Base):
    """RainMaker user — one per phone number"""
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    phone_number = Column(String(20), unique=True, nullable=False, index=True)
    cardano_address = Column(String(255), nullable=False)
    stake_address = Column(String(255), nullable=True)
    encrypted_seed = Column(Text, nullable=True)  # AES-256-GCM encrypted seed phrase
    pin_hash = Column(String(128), nullable=True)  # bcrypt hash of PIN
    handle_name = Column(String(64), nullable=True)
    kyc_level = Column(Integer, default=0)  # 0, 1, 2
    is_active = Column(Boolean, default=True)
    pin_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AddressBook(Base):
    """Phone number ↔ Cardano address mapping"""
    __tablename__ = "address_book"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    phone_number = Column(String(20), unique=True, nullable=False, index=True)
    cardano_address = Column(String(255), nullable=False)
    stake_address = Column(String(255), nullable=True)
    handle_name = Column(String(64), nullable=True)  # optional alias
    owner_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    is_verified = Column(Boolean, default=False)
    kyc_level = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Transaction(Base):
    """Transaction log"""
    __tablename__ = "transactions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    sender_phone = Column(String(20), nullable=False, index=True)
    recipient_input = Column(String(255), nullable=False)  # what user typed
    resolved_address = Column(String(255), nullable=True)  # actual Cardano address
    resolution_type = Column(String(20), default="phone")  # phone | handle | full_address
    amount = Column(Float, nullable=False)
    token = Column(String(20), default="DJED")
    cardano_tx_hash = Column(String(128), nullable=True)
    fee_djed = Column(Float, default=0.10)
    status = Column(String(20), default="pending")  # pending | confirmed | failed
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    confirmed_at = Column(DateTime, nullable=True)


# Database setup
def get_engine():
    settings = get_settings()
    db_url = settings.database_url

    # SQLCipher: pysqlcipher3 is incompatible with SQLAlchemy 2.x (create_function 4-arg issue).
    # For production: migrate to PostgreSQL with TLS + encryption-at-rest.
    # Currently: seed phrases encrypted with AES-256-GCM, PINs hashed with bcrypt,
    # phone numbers accessible for USSD routing (required for lookups).
    if db_url.startswith("sqlite"):
        return create_engine(
            db_url.replace("+aiosqlite", ""),
            connect_args={"check_same_thread": False},
        )
    return create_engine(db_url)


def get_session():
    engine = get_engine()
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()
