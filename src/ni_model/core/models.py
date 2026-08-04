import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    FetchedValue,
    Float,
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
    person_number = Column(
        BigInteger,
        nullable=True,
        unique=True,
        index=True,
        server_default=FetchedValue(),
    )
    run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("simulation_runs.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    baseline_profile = Column(String(32), nullable=False, default="current", index=True)
    age = Column(Integer, nullable=False)
    birth_year = Column(Integer, nullable=True, index=True)
    religious_background = Column(Enum(ReligiousBackground), nullable=False)
    probable_community = Column(Enum(ReligiousBackground), nullable=False)
    gender = Column(Enum(Gender), nullable=False)
    education_level = Column(Enum(EducationLevel), nullable=False)
    location = Column(Enum(Location), nullable=False)
    origin = Column(Enum(Origin), nullable=False)

    # Indexes for performance
    __table_args__ = (
        CheckConstraint(
            "probable_community <> 'NONE'",
            name="ck_person_probable_community_not_none",
        ),
        Index("idx_age", "age"),
        Index("idx_religious_background", "religious_background"),
        Index("idx_probable_community", "probable_community"),
        Index("idx_location", "location"),
        Index("idx_origin", "origin"),
        Index("idx_age_location", "age", "location"),
        Index("idx_religious_gender", "religious_background", "gender"),
        Index("idx_run_location", "run_id", "location"),
        Index("idx_run_age", "run_id", "age"),
    )

    def __init__(self, **kwargs):
        # Keep existing callers and fixtures meaningful: absent an explicit
        # estimate, the reported background is the best available value.
        if "probable_community" not in kwargs:
            reported = kwargs.get("religious_background")
            kwargs["probable_community"] = (
                ReligiousBackground.OTHER
                if reported == ReligiousBackground.NONE
                else reported
            )
        super().__init__(**kwargs)


class SimulationRun(Base):
    __tablename__ = "simulation_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_path = Column(String(255), nullable=False)
    start_year = Column(Integer, nullable=False)
    end_year = Column(Integer, nullable=False)
    status = Column(String(32), nullable=False, default="pending", index=True)
    owner_key = Column(String(64), nullable=True, index=True)
    base_population_count = Column(Integer, nullable=False, default=0)
    represented_population_count = Column(Integer, nullable=False, default=0)
    population_scale = Column(Float, nullable=False, default=1.0)
    baseline_profile = Column(String(32), nullable=False, default="current")
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
    person_events = relationship("SimulationPersonEvent", cascade="all, delete-orphan")
    checkpoints = relationship("SimulationCheckpoint", cascade="all, delete-orphan")


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


class SimulationPersonEvent(Base):
    """Append-only change to an individual during one simulation run."""

    __tablename__ = "simulation_person_events"

    id = Column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("simulation_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    person_id = Column(UUID(as_uuid=True), nullable=False)
    year = Column(Integer, nullable=False)
    event_type = Column(String(24), nullable=False)
    data = Column(JSON, nullable=False, default=dict)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        Index("idx_event_run_year_id", "run_id", "year", "id"),
        Index("idx_event_run_person_year", "run_id", "person_id", "year"),
    )


class SimulationCheckpoint(Base):
    """Metadata for a columnar full-population run checkpoint."""

    __tablename__ = "simulation_checkpoints"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("simulation_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    year = Column(Integer, nullable=False)
    storage_uri = Column(String(1000), nullable=False)
    population_count = Column(Integer, nullable=False)
    byte_size = Column(BigInteger, nullable=False)
    checksum = Column(String(64), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        UniqueConstraint("run_id", "year", name="uq_run_checkpoint_year"),
        Index("idx_checkpoint_run_year", "run_id", "year"),
    )
