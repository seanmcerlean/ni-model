import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from ..core.database import Base


class ReligiousBackground(enum.Enum):
    CATHOLIC = "catholic"
    PROTESTANT = "protestant"
    OTHER = "other"
    NONE = "none"


class Gender(enum.Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class EducationLevel(enum.Enum):
    PRE_PRIMARY = "pre_primary"
    PRIMARY = "primary"
    SECONDARY = "secondary"
    TERTIARY = "tertiary"
    POSTGRADUATE = "postgraduate"


class Location(enum.Enum):
    ANTRIM = "antrim"
    ARMAGH = "armagh"
    DOWN = "down"
    FERMANAGH = "fermanagh"
    DERRY = "derry"
    TYRONE = "tyrone"
    BELFAST_NORTH = "belfast_north"
    BELFAST_SOUTH = "belfast_south"
    BELFAST_EAST = "belfast_east"
    BELFAST_WEST = "belfast_west"


class Origin(enum.Enum):
    NI = "ni"
    ROI = "roi"
    GB = "gb"
    OTHER = "other"


class Person(Base):
    __tablename__ = "persons"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("simulation_runs.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    age = Column(Integer, nullable=False)
    religious_background = Column(Enum(ReligiousBackground), nullable=False)
    gender = Column(Enum(Gender), nullable=False)
    education_level = Column(Enum(EducationLevel), nullable=False)
    location = Column(Enum(Location), nullable=False)
    origin = Column(Enum(Origin), nullable=False)

    # Indexes for performance
    __table_args__ = (
        Index("idx_age", "age"),
        Index("idx_religious_background", "religious_background"),
        Index("idx_location", "location"),
        Index("idx_origin", "origin"),
        Index("idx_age_location", "age", "location"),
        Index("idx_religious_gender", "religious_background", "gender"),
        Index("idx_run_location", "run_id", "location"),
        Index("idx_run_age", "run_id", "age"),
    )


class SimulationRun(Base):
    __tablename__ = "simulation_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_path = Column(String(255), nullable=False)
    start_year = Column(Integer, nullable=False)
    end_year = Column(Integer, nullable=False)
    status = Column(String(32), nullable=False, default="pending", index=True)
    base_population_count = Column(Integer, nullable=False, default=0)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)
    error = Column(String(1000), nullable=True)

    persons = relationship("Person", cascade="all, delete-orphan")
    snapshots = relationship(
        "SimulationSnapshot",
        cascade="all, delete-orphan",
        order_by="SimulationSnapshot.year",
    )


class SimulationSnapshot(Base):
    __tablename__ = "simulation_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("simulation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    year = Column(Integer, nullable=False)
    data = Column(JSON, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    __table_args__ = (UniqueConstraint("run_id", "year", name="uq_run_snapshot_year"),)
