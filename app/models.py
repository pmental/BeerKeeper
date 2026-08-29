import datetime as dt

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


def utcnow():
    return dt.datetime.utcnow()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(32), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    oidc_subject = Column(String(255), unique=True, nullable=True, index=True)
    display_name = Column(String(255), nullable=True)  # from OIDC's "name" claim; falls back to username
    is_admin = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    # Account preferences
    default_sort = Column(String(16), default="beer", nullable=False)  # 'beer' | 'brewery' | 'drinkby'
    unit_system = Column(String(8), default="imperial", nullable=False)  # 'imperial' | 'metric'
    show_fridge_column = Column(Boolean, default=True, nullable=False)
    show_location_column = Column(Boolean, default=False, nullable=False)
    trading_enabled = Column(Boolean, default=False, nullable=False)
    messaging_enabled = Column(Boolean, default=True, nullable=False)

    # Visibility / privacy
    cellar_public = Column(Boolean, default=True, nullable=False)
    notes_public = Column(Boolean, default=False, nullable=False)
    drinkby_public = Column(Boolean, default=False, nullable=False)

    entries = relationship("CellarEntry", back_populates="user", cascade="all, delete-orphan")
    logs = relationship("ConsumptionLog", back_populates="user", cascade="all, delete-orphan")
    wanted = relationship("WantedEntry", back_populates="user", cascade="all, delete-orphan")


class Brewery(Base):
    __tablename__ = "breweries"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True, nullable=False, index=True)
    website = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    beers = relationship("Beer", back_populates="brewery")


class Beer(Base):
    __tablename__ = "beers"
    __table_args__ = (UniqueConstraint("name", "brewery_id", name="uq_beer_name_brewery"),)

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, index=True)
    brewery_id = Column(Integer, ForeignKey("breweries.id"), nullable=False)
    style = Column(String(120), nullable=True)
    abv = Column(Float, nullable=True)
    description = Column(Text, nullable=True)
    reference_url = Column(String(500), nullable=True)  # e.g. link to an external beer database entry
    created_at = Column(DateTime, default=utcnow, nullable=False)

    brewery = relationship("Brewery", back_populates="beers")
    entries = relationship("CellarEntry", back_populates="beer")
    logs = relationship("ConsumptionLog", back_populates="beer")


class CellarEntry(Base):
    """A held quantity of a beer, either In Cellar or In Fridge (or a custom location)."""

    __tablename__ = "cellar_entries"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    beer_id = Column(Integer, ForeignKey("beers.id"), nullable=False, index=True)

    location = Column(String(16), default="cellar", nullable=False)  # 'cellar' | 'fridge'
    custom_location = Column(String(120), nullable=True)

    quantity = Column(Integer, default=1, nullable=False)
    size_oz = Column(Float, nullable=True)
    bottle_date = Column(Date, nullable=True)
    best_before = Column(Date, nullable=True)
    batch_notes = Column(Text, nullable=True)

    trade_status = Column(String(8), default="none", nullable=False)  # 'none' | 'ft' | 'iso'

    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    user = relationship("User", back_populates="entries")
    beer = relationship("Beer", back_populates="entries")


class ConsumptionLog(Base):
    """A record of a beer being drunk. Stores the tasting note/rating independently
    of any CellarEntry so history survives entry deletion, per the FAQ behavior."""

    __tablename__ = "consumption_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    beer_id = Column(Integer, ForeignKey("beers.id"), nullable=False, index=True)

    quantity = Column(Integer, default=1, nullable=False)
    consumed_on = Column(Date, default=dt.date.today, nullable=False)
    note = Column(Text, nullable=True)
    rating = Column(Float, nullable=True)  # 0-5, half-star increments

    created_at = Column(DateTime, default=utcnow, nullable=False)

    user = relationship("User", back_populates="logs")
    beer = relationship("Beer", back_populates="logs")


class WantedEntry(Base):
    """A beer a user wants but does not currently own - distinct from a
    CellarEntry marked ISO (trade_status), which is for a beer you already
    have some of but want more. This is for "don't have it at all yet"."""

    __tablename__ = "wanted_entries"
    __table_args__ = (UniqueConstraint("user_id", "beer_id", name="uq_wanted_user_beer"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    beer_id = Column(Integer, ForeignKey("beers.id"), nullable=False, index=True)

    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    user = relationship("User", back_populates="wanted")
    beer = relationship("Beer")


class InstanceSettings(Base):
    """A single-row table (id is always 1) for instance-wide settings that
    an admin can change at runtime, as opposed to env-var config that needs
    a restart. Currently just the registration toggle, but built to hold
    more if that's ever needed."""

    __tablename__ = "instance_settings"

    id = Column(Integer, primary_key=True)
    registration_enabled = Column(Boolean, default=True, nullable=False)


class PasswordResetToken(Base):
    """A one-time, expiring token for the self-service "forgot password"
    flow. Only a SHA-256 hash of the token is stored - the raw token only
    ever exists in the emailed link, the same way a password itself is
    never stored in plain text."""

    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    user = relationship("User")
