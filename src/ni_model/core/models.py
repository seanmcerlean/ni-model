import enum
import uuid

from sqlalchemy import Column, Enum, Index, Integer
from sqlalchemy.dialects.postgresql import UUID

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
    )
