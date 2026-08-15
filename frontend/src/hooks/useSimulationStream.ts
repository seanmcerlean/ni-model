import { useCallback, useEffect, useRef, useState } from "react";

import { PopulationMode, SimulationAdjustments, StreamStatus, YearSnapshot } from "../types";
import { isStaticDeployment, loadRecordingManifest, RecordedScenarioData } from "../deployment";

export interface UseSimulationStream {
  snapshots: Record<number, YearSnapshot>;
  years: number[];
  status: StreamStatus;
  error: string | null;
  startStream: (startYear: number, endYear: number, modelPath?: string, adjustments?: SimulationAdjustments, populationMode?: PopulationMode) => void;
  abort: () => void;
  reset: () => void;
}

export function useSimulationStream(): UseSimulationStream {
  const [snapshots, setSnapshots] = useState<Record<number, YearSnapshot>>({});
  const [years, setYears] = useState<number[]>([]);
  const [status, setStatus] = useState<StreamStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const esRef = useRef<EventSource | null>(null);
  const fetchRef = useRef<AbortController | null>(null);
  const runIdRef = useRef<string | null>(null);

  const cancelActive = useCallback(() => {
    esRef.current?.close();
    esRef.current = null;
    fetchRef.current?.abort();
    fetchRef.current = null;
    if (runIdRef.current) {
      void fetch(`/api/simulation/runs/${runIdRef.current}/cancel`, {
        method: "POST",
        keepalive: true,
      });
      runIdRef.current = null;
    }
  }, []);

  const abort = useCallback(() => {
    cancelActive();
    setStatus((s) => (s === "streaming" ? "idle" : s));
  }, [cancelActive]);

  const reset = useCallback(() => {
    cancelActive();
    setSnapshots({});
    setYears([]);
    setError(null);
    setStatus("idle");
  }, [cancelActive]);

  useEffect(() => () => cancelActive(), [cancelActive]);

  const startStream = useCallback(
    (
      startYear: number,
      endYear: number,
      modelPath = "models/ni_base_2024.yaml",
      adjustments?: SimulationAdjustments,
      populationMode: PopulationMode = "sample",
    ) => {
      cancelActive();
      setSnapshots({});
      setYears([]);
      setError(null);
      setStatus("streaming");
      runIdRef.current = null;

      if (isStaticDeployment) {
        const controller = new AbortController();
        fetchRef.current = controller;
        void loadRecordingManifest()
          .then((manifest) => {
            const scenario = manifest.scenarios.find(
              (item) => item.model_path === modelPath,
            );
            if (!scenario) throw new Error("No recording exists for this model and seed.");
            return fetch(scenario.asset, { signal: controller.signal });
          })
          .then((response) => {
            if (!response.ok) throw new Error("Could not load the recorded simulation.");
            return response.json() as Promise<RecordedScenarioData>;
          })
          .then((recording) => {
            if (controller.signal.aborted || fetchRef.current !== controller) return;
            const selected = recording.snapshots.filter(
              (snapshot) => snapshot.year >= startYear && snapshot.year <= endYear,
            );
            setSnapshots(Object.fromEntries(selected.map((snapshot) => [snapshot.year, snapshot])));
            setYears(selected.map((snapshot) => snapshot.year).sort((a, b) => a - b));
            setStatus("complete");
            fetchRef.current = null;
          })
          .catch((caught: Error) => {
            if (caught.name === "AbortError" || fetchRef.current !== controller) return;
            setError(caught.message);
            setStatus("error");
            fetchRef.current = null;
          });
        return;
      }

      const params = new URLSearchParams({
        start_year: String(startYear),
        end_year: String(endYear),
        model_path: modelPath,
      });
      if (adjustments) {
        params.set("birth_multiplier", String(adjustments.birth_multiplier));
        params.set("death_multiplier", String(adjustments.death_multiplier));
        params.set("migration_multiplier", String(adjustments.migration_multiplier));
        params.set("relocation_multiplier", String(adjustments.relocation_multiplier));
        params.set("integration_multiplier", String(adjustments.integration_multiplier ?? 1));
        params.set("community_adjustments", JSON.stringify(adjustments.community));
        if (adjustments.random_seed != null) params.set("random_seed", String(adjustments.random_seed));
      }
      if (populationMode === "sample") params.set("population_limit", "25000");
      const es = new EventSource(`/api/simulation/stream?${params}`);
      esRef.current = es;

      es.onmessage = (e) => {
        if (esRef.current !== es) return;
        let snap: YearSnapshot;
        try {
          snap = JSON.parse(e.data) as YearSnapshot;
        } catch {
          cancelActive();
          setError("The server returned malformed simulation data.");
          setStatus("error");
          return;
        }
        if (snap.run_id) runIdRef.current = snap.run_id;
        setSnapshots((prev) => ({ ...prev, [snap.year]: snap }));
        setYears((prev) =>
          prev.includes(snap.year) ? prev : [...prev, snap.year].sort((a, b) => a - b)
        );
      };

      es.addEventListener("started", (event) => {
        if (esRef.current !== es) return;
        const message = event as MessageEvent<string>;
        try {
          runIdRef.current = (JSON.parse(message.data) as { run_id: string }).run_id;
        } catch {
          cancelActive();
          setError("The server returned malformed simulation metadata.");
          setStatus("error");
        }
      });

      es.addEventListener("complete", () => {
        if (esRef.current !== es) return;
        es.close();
        esRef.current = null;
        runIdRef.current = null;
        setStatus("complete");
      });

      es.addEventListener("cancelled", () => {
        if (esRef.current !== es) return;
        es.close();
        esRef.current = null;
        runIdRef.current = null;
        setStatus("idle");
      });

      es.onerror = () => {
        if (esRef.current !== es) return;
        cancelActive();
        setError("Stream error — check server connection");
        setStatus("error");
      };
    },
    [cancelActive]
  );

  return { snapshots, years, status, error, startStream, abort, reset };
}
