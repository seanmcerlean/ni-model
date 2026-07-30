export interface SimulationYearResult {
  year: number;
  births: number;
  deaths: number;
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
  simulation_result?: SimulationYearResult;
}

export interface LocationDetail {
  location: string;
  total: number;
  religious_breakdown: Record<string, number>;
  gender_breakdown: Record<string, number>;
  origin_breakdown: Record<string, number>;
  age_bands: Record<string, number>;
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
