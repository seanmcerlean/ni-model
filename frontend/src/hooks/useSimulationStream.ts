import { useCallback, useRef, useState } from "react";

import { PopulationMode, SimulationAdjustments, StreamStatus, YearSnapshot } from "../types";

export interface UseSimulationStream {
  snapshots: Record<number, YearSnapshot>;
  years: number[];
  status: StreamStatus;
  error: string | null;
  startStream: (startYear: number, endYear: number, modelPath?: string, adjustments?: SimulationAdjustments, populationMode?: PopulationMode) => void;
  abort: () => void;
}

export function useSimulationStream(): UseSimulationStream {
  const [snapshots, setSnapshots] = useState<Record<number, YearSnapshot>>({});
  const [years, setYears] = useState<number[]>([]);
  const [status, setStatus] = useState<StreamStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const esRef = useRef<EventSource | null>(null);
  const runIdRef = useRef<string | null>(null);

  const abort = useCallback(() => {
    esRef.current?.close();
    esRef.current = null;
    if (runIdRef.current) {
      void fetch(`/api/simulation/runs/${runIdRef.current}/cancel`, {
        method: "POST",
        keepalive: true,
      });
      runIdRef.current = null;
    }
    setStatus((s) => (s === "streaming" ? "idle" : s));
  }, []);

  const startStream = useCallback(
    (
      startYear: number,
      endYear: number,
      modelPath = "models/ni_base_2024.yaml",
      adjustments?: SimulationAdjustments,
      populationMode: PopulationMode = "sample",
    ) => {
      esRef.current?.close();
      setSnapshots({});
      setYears([]);
      setError(null);
      setStatus("streaming");
      runIdRef.current = null;

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
        params.set("community_adjustments", JSON.stringify(adjustments.community));
        if (adjustments.random_seed !== null) params.set("random_seed", String(adjustments.random_seed));
      }
      if (populationMode === "sample") params.set("population_limit", "25000");
      const es = new EventSource(`/api/simulation/stream?${params}`);
      esRef.current = es;

      es.onmessage = (e) => {
        const snap: YearSnapshot = JSON.parse(e.data);
        if (snap.run_id) runIdRef.current = snap.run_id;
        setSnapshots((prev) => ({ ...prev, [snap.year]: snap }));
        setYears((prev) =>
          prev.includes(snap.year) ? prev : [...prev, snap.year].sort((a, b) => a - b)
        );
      };

      es.addEventListener("started", (event) => {
        const message = event as MessageEvent<string>;
        runIdRef.current = (JSON.parse(message.data) as { run_id: string }).run_id;
      });

      es.addEventListener("complete", () => {
        es.close();
        esRef.current = null;
        runIdRef.current = null;
        setStatus("complete");
      });

      es.addEventListener("cancelled", () => {
        es.close();
        esRef.current = null;
        runIdRef.current = null;
        setStatus("idle");
      });

      es.onerror = () => {
        es.close();
        esRef.current = null;
        setError("Stream error — check server connection");
        setStatus("error");
      };
    },
    []
  );

  return { snapshots, years, status, error, startStream, abort };
}
