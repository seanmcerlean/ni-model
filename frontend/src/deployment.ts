import { SimulationModel, YearSnapshot } from "./types";

export type DeploymentMode = "static" | "parquet" | "full";
export const STATIC_SEEDS = [1180, 1690, 1921, 1969] as const;

export const DEPLOYMENT_MODE: DeploymentMode =
  (import.meta.env.VITE_DEPLOYMENT_MODE as DeploymentMode | undefined) ?? "parquet";

export interface RecordedScenario {
  id: string;
  model_path: string;
  asset: string;
  seed: number;
  start_year: number;
  end_year: number;
  population_size: number;
  final_population_size?: number;
}

export interface RecordingManifest {
  schema_version: number;
  models: SimulationModel[];
  scenarios: RecordedScenario[];
}

export interface RecordedScenarioData {
  scenario: RecordedScenario;
  snapshots: YearSnapshot[];
}

export const isStaticDeployment = DEPLOYMENT_MODE === "static";

export async function loadRecordingManifest(): Promise<RecordingManifest> {
  const response = await fetch("/recordings/manifest.json");
  if (!response.ok) throw new Error("Could not load the recorded scenario catalogue.");
  return response.json() as Promise<RecordingManifest>;
}
