import { SimulationModel, YearSnapshot } from "./types";

export type DeploymentMode = "static" | "parquet" | "full";

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
  const manifest = await response.json() as Partial<RecordingManifest>;
  if (
    manifest.schema_version !== 1
    || !Array.isArray(manifest.models)
    || !Array.isArray(manifest.scenarios)
  ) {
    throw new Error("The recorded scenario catalogue is incompatible or malformed.");
  }
  const modelPaths = new Set(manifest.models.map((model) => model.path));
  const scenarioPaths = new Set(manifest.scenarios.map((scenario) => scenario.model_path));
  if (
    manifest.scenarios.length !== manifest.models.length
    || modelPaths.size !== manifest.models.length
    || scenarioPaths.size !== manifest.scenarios.length
    || [...modelPaths].some((path) => !scenarioPaths.has(path))
  ) {
    throw new Error("The recorded scenario catalogue does not cover every model exactly once.");
  }
  return manifest as RecordingManifest;
}
