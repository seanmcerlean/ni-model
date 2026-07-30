import { useCallback, useEffect, useRef, useState } from "react";

import { Controls } from "./components/Controls";
import { LocationDetail } from "./components/LocationDetail";
import { NiMap } from "./components/NiMap";
import { useSimulationStream } from "./hooks/useSimulationStream";
import { PlaybackSpeed, YearSnapshot } from "./types";

export default function App() {
  const { snapshots, years, status, startStream, abort } = useSimulationStream();

  const [startYear, setStartYear] = useState(1969);
  const [endYear, setEndYear] = useState(2030);
  const [currentYear, setCurrentYear] = useState<number | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [speed, setSpeed] = useState<PlaybackSpeed>(1);
  const [selectedLocation, setSelectedLocation] = useState<string | null>(null);

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const snapshot: YearSnapshot | null =
    currentYear !== null ? (snapshots[currentYear] ?? null) : null;

  // Auto-advance to first buffered year when stream starts
  useEffect(() => {
    if (years.length > 0 && currentYear === null) {
      setCurrentYear(years[0]);
    }
  }, [years, currentYear]);

  // Playback ticker
  useEffect(() => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    if (!isPlaying) return;

    intervalRef.current = setInterval(() => {
      setCurrentYear((prev) => {
        if (prev === null) return years[0] ?? null;
        const idx = years.indexOf(prev);
        const next = years[idx + 1];
        if (next === undefined) {
          setIsPlaying(false);
          return prev;
        }
        return next;
      });
    }, 1000 / speed);

    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [isPlaying, speed, years]);

  const handleStartStream = useCallback(() => {
    setCurrentYear(null);
    setIsPlaying(false);
    startStream(startYear, endYear);
  }, [startYear, endYear, startStream]);

  const handlePlayPause = useCallback(() => {
    setIsPlaying((p) => !p);
  }, []);

  const handleScrub = useCallback((year: number) => {
    // Snap to nearest buffered year
    const nearest = years.reduce((a, b) =>
      Math.abs(b - year) < Math.abs(a - year) ? b : a,
      years[0]
    );
    if (nearest !== undefined) setCurrentYear(nearest);
  }, [years]);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh" }}>
      <header style={styles.header}>
        <span style={styles.title}>NI Population Model</span>
        {currentYear && (
          <span style={styles.yearBadge}>{currentYear}</span>
        )}
        {status === "streaming" && (
          <button style={styles.abortBtn} onClick={abort}>Stop</button>
        )}
      </header>

      <div style={{ flex: 1, position: "relative" }}>
        <NiMap snapshot={snapshot} onLocationClick={setSelectedLocation} />
        <LocationDetail
          locationId={selectedLocation}
          onClose={() => setSelectedLocation(null)}
        />
      </div>

      <Controls
        status={status}
        years={years}
        currentYear={currentYear}
        isPlaying={isPlaying}
        speed={speed}
        startYear={startYear}
        endYear={endYear}
        onStartStream={handleStartStream}
        onPlayPause={handlePlayPause}
        onSpeedChange={setSpeed}
        onScrub={handleScrub}
        onStartYearChange={setStartYear}
        onEndYearChange={setEndYear}
      />
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  header: {
    background: "#0f3460",
    padding: "8px 16px",
    display: "flex",
    alignItems: "center",
    gap: 12,
    borderBottom: "1px solid #333",
  },
  title: { fontWeight: "bold", fontSize: 16, color: "#eee" },
  yearBadge: {
    background: "#e94560",
    color: "#fff",
    borderRadius: 4,
    padding: "2px 10px",
    fontWeight: "bold",
    fontSize: 15,
  },
  abortBtn: {
    marginLeft: "auto",
    background: "#333",
    color: "#eee",
    border: "1px solid #555",
    borderRadius: 4,
    padding: "3px 10px",
    cursor: "pointer",
  },
};
