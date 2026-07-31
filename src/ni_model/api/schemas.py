from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AgeStats(BaseModel):
    average: float
    minimum: int
    maximum: int


class PopulationSummary(BaseModel):
    total_population: int
    age_stats: AgeStats
    religious_breakdown: Dict[str, int]
    gender_breakdown: Dict[str, int]


class LocationSummary(BaseModel):
    location: str
    total: int
    religious_breakdown: Dict[str, int]


class LocationDetail(BaseModel):
    location: str
    total: int
    religious_breakdown: Dict[str, int]
    gender_breakdown: Dict[str, int]
    origin_breakdown: Dict[str, int]
    age_bands: Dict[str, int]


class SimulationYearResult(BaseModel):
    year: int
    births: int
    deaths: int
    immigration: int = 0
    emigration: int = 0
    migration: int
    internal_migration: int
    net_change: int


class SimulationLocationSnapshot(BaseModel):
    total: int
    religious_breakdown: Dict[str, int]
    gender_breakdown: Dict[str, int]
    origin_breakdown: Dict[str, int]
    age_bands: Dict[str, int]


class SimulationYearSnapshot(BaseModel):
    run_id: Optional[UUID] = None
    year: int
    total_population: int
    religious_breakdown: Dict[str, int]
    gender_breakdown: Dict[str, int]
    location_breakdown: Dict[str, int]
    locations: Dict[str, SimulationLocationSnapshot] = Field(default_factory=dict)
    voting_predictions: Dict[str, "VotingPrediction"] = Field(default_factory=dict)
    simulation_result: Optional[SimulationYearResult] = None


class SimulationModelSummary(BaseModel):
    id: str
    path: str
    name: str
    description: str
    rate_jitter: float
    random_seed: Optional[int]
    baseline_year: Optional[int] = None
    data_through: Optional[int] = None
    projection_version: Optional[str] = None
    default_start_year: Optional[int] = None
    default_end_year: Optional[int] = None
    birth_rules: int
    death_rules: int
    migration_rules: int
    internal_migration_rules: int
    birth_rate_rules: List[Dict[str, Any]]
    death_rate_rules: List[Dict[str, Any]]
    migration_rate_rules: List[Dict[str, Any]]
    internal_migration_rate_rules: List[Dict[str, Any]]
    year_min: Optional[int]
    year_max: Optional[int]


class SimulationYearsList(BaseModel):
    years: List[int]


class CommunityRateAdjustments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    birth_multiplier: float = Field(default=1.0, ge=0.0, le=3.0)
    death_multiplier: float = Field(default=1.0, ge=0.0, le=3.0)
    migration_multiplier: float = Field(default=1.0, ge=0.0, le=3.0)
    relocation_multiplier: float = Field(default=1.0, ge=0.0, le=3.0)


class CommunityAdjustments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    catholic: CommunityRateAdjustments = Field(default_factory=CommunityRateAdjustments)
    protestant: CommunityRateAdjustments = Field(
        default_factory=CommunityRateAdjustments
    )
    other: CommunityRateAdjustments = Field(default_factory=CommunityRateAdjustments)
    none: CommunityRateAdjustments = Field(default_factory=CommunityRateAdjustments)


class SimulationAdjustments(BaseModel):
    birth_multiplier: float = Field(default=1.0, ge=0.0, le=3.0)
    death_multiplier: float = Field(default=1.0, ge=0.0, le=3.0)
    migration_multiplier: float = Field(default=1.0, ge=0.0, le=3.0)
    relocation_multiplier: float = Field(default=1.0, ge=0.0, le=3.0)
    random_seed: Optional[int] = None
    community: Optional[CommunityAdjustments] = None


class SimulationRunRequest(BaseModel):
    model_path: str = "models/ni_base_2024.yaml"
    start_year: int = 2024
    end_year: int = 2030
    adjustments: SimulationAdjustments = Field(default_factory=SimulationAdjustments)

    @field_validator("end_year")
    @classmethod
    def end_after_start(cls, v, info):
        if "start_year" in info.data and v < info.data["start_year"]:
            raise ValueError("end_year must be >= start_year")
        return v

    @field_validator("start_year", "end_year")
    @classmethod
    def reasonable_year(cls, v):
        if not (1900 <= v <= 2200):
            raise ValueError("year must be between 1900 and 2200")
        return v


class SimulationRunResponse(BaseModel):
    run_id: UUID
    status: str
    model_path: str
    start_year: int
    end_year: int
    years_simulated: int
    results: List[SimulationYearResult]


class SimulationRunSummary(BaseModel):
    run_id: UUID
    model_path: str
    start_year: int
    end_year: int
    status: str
    base_population_count: int
    completed_years: List[int]
    error: Optional[str] = None
    adjustments: Dict[str, Any] = Field(default_factory=dict)


class LocationVotePrediction(BaseModel):
    eligible_population: int
    projected_turnout: int
    turnout_rate: float
    unite: int
    remain: int
    undecided: int
    unite_share: float
    remain_share: float
    undecided_share: float
    decided_unite_share: float
    intervals: Dict[str, Dict[str, float]]
    scenarios: List[Dict[str, Any]]


class VotingPrediction(BaseModel):
    total_population: int
    eligible_population: int
    projected_turnout: int
    turnout_rate: float
    unite: int
    remain: int
    undecided: int
    unite_share: float
    remain_share: float
    undecided_share: float
    decided_unite_share: float
    intervals: Dict[str, Dict[str, float]]
    scenarios: List[Dict[str, Any]]
    source: Dict[str, Any]
    limitations: str
    by_location: Dict[str, LocationVotePrediction]
