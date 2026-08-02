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
    community_transitions: int = 0
    community_transition_breakdown: Dict[str, int] = Field(default_factory=dict)
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
    sample_population: Optional[int] = None
    population_scale: float = 1.0
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
    baseline_profile: str
    baseline_population: int
    data_through: Optional[int] = None
    projection_version: Optional[str] = None
    default_start_year: Optional[int] = None
    default_end_year: Optional[int] = None
    birth_rules: int
    death_rules: int
    migration_rules: int
    internal_migration_rules: int
    integration_rules: int = 0
    child_background_rules: int = 0
    birth_rate_rules: List[Dict[str, Any]]
    death_rate_rules: List[Dict[str, Any]]
    mortality_age_rates: List[Dict[str, Any]] = Field(default_factory=list)
    migration_rate_rules: List[Dict[str, Any]]
    internal_migration_rate_rules: List[Dict[str, Any]]
    integration_rate_rules: List[Dict[str, Any]] = Field(default_factory=list)
    child_background_rule_details: List[Dict[str, Any]] = Field(default_factory=list)
    year_min: Optional[int]
    year_max: Optional[int]


class SimulationYearsList(BaseModel):
    years: List[int]


class SimulationPerson(BaseModel):
    person_id: UUID
    person_number: Optional[int] = None
    birth_year: int
    age: int
    religious_background: str
    gender: str
    education_level: str
    location: str
    origin: str


class SimulationPeoplePage(BaseModel):
    run_id: UUID
    year: int
    total: int
    offset: int
    limit: int
    people: List[SimulationPerson]


class SimulationPersonEventSummary(BaseModel):
    year: int
    event_type: str
    data: Dict[str, Any]


class SimulationPersonHistory(BaseModel):
    person_id: UUID
    initial: Dict[str, Any]
    events: List[SimulationPersonEventSummary]


class CommunityRateAdjustments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    birth_multiplier: float = Field(default=1.0, ge=0.0, le=3.0)
    death_multiplier: float = Field(default=1.0, ge=0.0, le=3.0)
    migration_multiplier: float = Field(default=1.0, ge=0.0, le=3.0)
    relocation_multiplier: float = Field(default=1.0, ge=0.0, le=3.0)
    integration_multiplier: float = Field(default=1.0, ge=0.0, le=3.0)


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
    integration_multiplier: float = Field(default=1.0, ge=0.0, le=3.0)
    random_seed: Optional[int] = None
    community: Optional[CommunityAdjustments] = None


class SimulationRunRequest(BaseModel):
    model_path: str = "models/ni_current.yaml"
    start_year: int = 2024
    end_year: int = 2030
    adjustments: SimulationAdjustments = Field(default_factory=SimulationAdjustments)
    population_limit: Optional[int] = Field(default=None, ge=1, le=1_903_175)

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
    represented_population_count: int
    population_scale: float
    baseline_profile: str
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
