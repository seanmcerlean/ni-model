export interface SimulationYearResult {
  year: number;
  births: number;
  deaths: number;
  immigration: number;
  emigration: number;
  migration: number;
  internal_migration: number;
  net_change: number;
}

export interface YearSnapshot {
  year: number;
  total_population: number;
  religious_breakdown: Record<string, number>;
  gender_breakdown: Record<string, number>;
  location_breakdown: Record<string, number>;
  locations?: Record<string, SimulationLocationSnapshot>;
  simulation_result?: SimulationYearResult;
}

export interface SimulationLocationSnapshot {
  total: number;
  religious_breakdown: Record<string, number>;
  gender_breakdown: Record<string, number>;
  origin_breakdown: Record<string, number>;
  age_bands: Record<string, number>;
}

export interface SimulationModel {
  id: string;
  path: string;
  name: string;
  description: string;
  rate_jitter: number;
  random_seed: number | null;
  birth_rules: number;
  death_rules: number;
  migration_rules: number;
  internal_migration_rules: number;
  year_min: number | null;
  year_max: number | null;
}

export type PlaybackSpeed = 0.5 | 1 | 2 | 5;
export type StreamStatus = "idle" | "streaming" | "complete" | "error";

export const LOCATION_KEYS: Record<string, string> = {
  belfast_north: "Belfast North",
  belfast_south: "Belfast South",
  belfast_east: "Belfast East",
  belfast_west: "Belfast West",
  antrim: "Antrim",
  armagh: "Armagh",
  derry: "Derry",
  down: "Down",
  fermanagh: "Fermanagh",
  tyrone: "Tyrone",
};
