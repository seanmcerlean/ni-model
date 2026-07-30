import { useCallback, useRef, useState } from "react";

import { YearSnapshot } from "../types";

export type StreamStatus = "idle" | "streaming" | "complete" | "error";

export interface UseSimulationStream {
  snapshots: Record<number, YearSnapshot>;
  years: number[];
  status: StreamStatus;
  error: string | null;
  startStream: (startYear: number, endYear: number, modelPath?: string) => void;
  abort: () => void;
}

export function useSimulationStream(): UseSimulationStream {
  const [snapshots, setSnapshots] = useState<Record<number, YearSnapshot>>({});
  const [years, setYears] = useState<number[]>([]);
  const [status, setStatus] = useState<StreamStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const esRef = useRef<EventSource | null>(null);

  const abort = useCallback(() => {
    esRef.current?.close();
    esRef.current = null;
    setStatus((s) => (s === "streaming" ? "idle" : s));
  }, []);

  const startStream = useCallback(
    (
      startYear: number,
      endYear: number,
      modelPath = "models/ni_base_2024.yaml"
    ) => {
      esRef.current?.close();
      setSnapshots({});
      setYears([]);
      setError(null);
      setStatus("streaming");

      const params = new URLSearchParams({
        start_year: String(startYear),
        end_year: String(endYear),
        model_path: modelPath,
      });
      const es = new EventSource(`/api/simulation/stream?${params}`);
      esRef.current = es;

      es.onmessage = (e) => {
        const snap: YearSnapshot = JSON.parse(e.data);
        setSnapshots((prev) => ({ ...prev, [snap.year]: snap }));
        setYears((prev) =>
          prev.includes(snap.year) ? prev : [...prev, snap.year].sort((a, b) => a - b)
        );
      };

      es.addEventListener("complete", () => {
        es.close();
        esRef.current = null;
        setStatus("complete");
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
