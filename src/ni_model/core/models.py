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
    ANTRIM_AND_NEWTOWNABBEY = "antrim_and_newtownabbey"
    ARMAGH_BANBRIDGE_CRAIGAVON = "armagh_banbridge_craigavon"
    BELFAST = "belfast"
    CAUSEWAY_COAST_GLENS = "causeway_coast_glens"
    DERRY_STRABANE = "derry_strabane"
    FERMANAGH_OMAGH = "fermanagh_omagh"
    LISBURN_CASTLEREAGH = "lisburn_castlereagh"
    MID_EAST_ANTRIM = "mid_east_antrim"
    MID_ULSTER = "mid_ulster"
    NEWRY_MOURNE_DOWN = "newry_mourne_down"
    ARDS_NORTH_DOWN = "ards_north_down"


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
    adjustments = Column(JSON, nullable=False, default=dict)

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
