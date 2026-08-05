export interface SimulationYearResult {
  year: number;
  births: number;
  deaths: number;
  immigration: number;
  emigration: number;
  migration: number;
  internal_migration: number;
  community_transitions?: number;
  community_transition_breakdown?: Record<string, number>;
  net_change: number;
}

export interface YearSnapshot {
  run_id?: string;
  year: number;
  total_population: number;
  sample_population?: number;
  population_scale?: number;
  religious_breakdown: Record<string, number>;
  probable_community_breakdown?: Record<string, number>;
  gender_breakdown: Record<string, number>;
  location_breakdown: Record<string, number>;
  locations?: Record<string, SimulationLocationSnapshot>;
  voting_predictions?: Record<string, VotingPrediction>;
  simulation_result?: SimulationYearResult;
}

export interface VotingPrediction {
  eligible_population: number;
  projected_turnout: number;
  turnout_rate: number;
  unite_share: number;
  remain_share: number;
  undecided_share: number;
  decided_unite_share: number;
  intervals: Record<string, { low: number; estimate: number; high: number }>;
  scenarios: Array<{ id: string; label: string; unite_share: number }>;
  source: { id: string; name: string; sample_size: number; fieldwork: string; url: string; community_basis?: CommunityBasis; community_basis_estimated?: boolean };
  limitations: string;
  by_location?: Record<string, LocationVotingPrediction>;
}

export type LocationVotingPrediction = Omit<
  VotingPrediction,
  "source" | "limitations" | "by_location"
>;

export interface SimulationLocationSnapshot {
  total: number;
  religious_breakdown: Record<string, number>;
  probable_community_breakdown?: Record<string, number>;
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
  baseline_year: number | null;
  baseline_profile: "current" | "historical";
  baseline_population: number;
  data_through: number | null;
  projection_version: string | null;
  default_start_year: number | null;
  default_end_year: number | null;
  birth_rules: number;
  death_rules: number;
  migration_rules: number;
  internal_migration_rules: number;
  integration_rules?: number;
  child_background_rules?: number;
  birth_rate_rules: ModelRule[];
  death_rate_rules: ModelRule[];
  mortality_age_rates?: ModelRule[];
  migration_rate_rules: ModelRule[];
  internal_migration_rate_rules: ModelRule[];
  integration_rate_rules?: ModelRule[];
  child_background_rule_details?: ChildBackgroundRule[];
  year_min: number | null;
  year_max: number | null;
}

export interface ChildBackgroundRule {
  year_min?: number;
  year_max?: number;
  source: string;
  probabilities: Record<string, number>;
}

export interface ModelRule {
  rate: number;
  age_min?: number;
  age_max?: number;
  year_min?: number;
  year_max?: number;
  destination?: string;
  evidence?: "observed" | "observed_net_only" | "principal_projection" | "census_2021_origin_destination" | "census_2021_origin_destination_by_religion" | "estimated_community_differential" | "estimated_identity_transition" | "nisra_2022_lgd_principal_projection";
  flow?: "in" | "out";
  filters?: Record<string, string | number>;
}

export type PlaybackSpeed = 0.5 | 1 | 2 | 5;
export type PopulationMode = "sample" | "full";
export type StreamStatus = "idle" | "streaming" | "complete" | "error";

export interface SimulationAdjustments {
  birth_multiplier: number;
  death_multiplier: number;
  migration_multiplier: number;
  relocation_multiplier: number;
  integration_multiplier?: number;
  random_seed: number | null;
  community: Record<CommunityBackground, CommunityRateAdjustments>;
}

export type CommunityBackground = "catholic" | "protestant" | "other" | "none";
export type CommunityBasis = "reported" | "probable";

export interface CommunityRateAdjustments {
  birth_multiplier: number;
  death_multiplier: number;
  migration_multiplier: number;
  relocation_multiplier: number;
  integration_multiplier?: number;
}

export const LOCATION_KEYS: Record<string, string> = {
  antrim_and_newtownabbey: "Antrim and Newtownabbey",
  armagh_banbridge_craigavon: "Armagh City, Banbridge and Craigavon",
  belfast: "Belfast",
  causeway_coast_glens: "Causeway Coast and Glens",
  derry_strabane: "Derry City and Strabane",
  fermanagh_omagh: "Fermanagh and Omagh",
  lisburn_castlereagh: "Lisburn and Castlereagh",
  mid_east_antrim: "Mid and East Antrim",
  mid_ulster: "Mid Ulster",
  newry_mourne_down: "Newry, Mourne and Down",
  ards_north_down: "Ards and North Down",
};

export const LOCATION_CODES: Record<string, string> = {
  N09000001: "antrim_and_newtownabbey",
  N09000002: "armagh_banbridge_craigavon",
  N09000003: "belfast",
  N09000004: "causeway_coast_glens",
  N09000005: "derry_strabane",
  N09000006: "fermanagh_omagh",
  N09000007: "lisburn_castlereagh",
  N09000008: "mid_east_antrim",
  N09000009: "mid_ulster",
  N09000010: "newry_mourne_down",
  N09000011: "ards_north_down",
};
