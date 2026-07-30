from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


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
    year: int
    total_population: int
    religious_breakdown: Dict[str, int]
    gender_breakdown: Dict[str, int]
    location_breakdown: Dict[str, int]
    locations: Dict[str, SimulationLocationSnapshot] = Field(default_factory=dict)
    simulation_result: Optional[SimulationYearResult] = None


class SimulationModelSummary(BaseModel):
    id: str
    path: str
    name: str
    description: str
    rate_jitter: float
    random_seed: Optional[int]
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


class SimulationRunRequest(BaseModel):
    model_path: str = "models/ni_base_2024.yaml"
    start_year: int = 2024
    end_year: int = 2030

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
    model_path: str
    start_year: int
    end_year: int
    years_simulated: int
    results: List[SimulationYearResult]


class LocationVotePrediction(BaseModel):
    total: int
    unite_share: float
    remain_share: float
    undecided_share: float


class VotingPrediction(BaseModel):
    total_population: int
    unite: int
    remain: int
    undecided: int
    unite_share: float
    remain_share: float
    undecided_share: float
    by_location: Dict[str, LocationVotePrediction]
