import { useCallback, useEffect, useRef, useState } from "react";

import "./app.css";
import { Controls } from "./components/Controls";
import { LocationDetail } from "./components/LocationDetail";
import { NiMap } from "./components/NiMap";
import { useSimulationStream } from "./hooks/useSimulationStream";
import { PlaybackSpeed, SimulationModel, YearSnapshot } from "./types";

export default function App() {
  const { snapshots, years, status, startStream, abort } = useSimulationStream();

  const [startYear, setStartYear] = useState(1969);
  const [endYear, setEndYear] = useState(2030);
  const [currentYear, setCurrentYear] = useState<number | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [speed, setSpeed] = useState<PlaybackSpeed>(1);
  const [selectedLocation, setSelectedLocation] = useState<string | null>(null);
  const [models, setModels] = useState<SimulationModel[]>([]);
  const [modelPath, setModelPath] = useState("models/ni_base_2024.yaml");

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const snapshot: YearSnapshot | null =
    currentYear !== null ? (snapshots[currentYear] ?? null) : null;
  const selectedModel = models.find((model) => model.path === modelPath);

  useEffect(() => {
    fetch("/api/simulation/models")
      .then((response) => response.json())
      .then((availableModels: SimulationModel[]) => setModels(availableModels))
      .catch(() => setModels([]));
  }, []);

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
    startStream(startYear, endYear, modelPath);
  }, [startYear, endYear, modelPath, startStream]);

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
    <div className="app-shell">
      <header className="app-header">
        <div>
          <span className="brand-kicker">DEMOGRAPHIC SCENARIO LAB</span>
          <div className="brand-title">Northern Ireland Population Model</div>
        </div>
        {currentYear && (
          <span className="year-badge">{currentYear}</span>
        )}
        {status === "streaming" && (
          <button className="stop-button" onClick={abort}>Stop simulation</button>
        )}
      </header>

      <div className="workspace">
        <aside className="model-panel">
          <div className="panel-kicker">MODEL</div>
          <label className="field-label" htmlFor="model-select">Scenario definition</label>
          <select
            id="model-select"
            className="model-select"
            value={modelPath}
            onChange={(event) => setModelPath(event.target.value)}
          >
            {models.length === 0 && <option value={modelPath}>NI Historical Model</option>}
            {models.map((model) => <option key={model.id} value={model.path}>{model.name}</option>)}
          </select>
          {selectedModel && (
            <>
              <p className="model-description">{selectedModel.description}</p>
              <dl className="model-facts">
                <div><dt>Seed</dt><dd>{selectedModel.random_seed ?? "Random"}</dd></div>
                <div><dt>Rate jitter</dt><dd>±{(selectedModel.rate_jitter * 100).toFixed(0)}%</dd></div>
                <div><dt>Birth rules</dt><dd>{selectedModel.birth_rules}</dd></div>
                <div><dt>Mortality rules</dt><dd>{selectedModel.death_rules}</dd></div>
                <div><dt>Migration rules</dt><dd>{selectedModel.migration_rules + selectedModel.internal_migration_rules}</dd></div>
              </dl>
              <div className="model-note">Rates are scenario assumptions per 1,000, not an official forecast.</div>
            </>
          )}
        </aside>

        <main className="map-column">
          <OverallStats snapshot={snapshot} />
          <div className="map-frame">
            <NiMap snapshot={snapshot} onLocationClick={setSelectedLocation} />
            <LocationDetail
              locationId={selectedLocation}
              year={currentYear}
              detail={selectedLocation && snapshot ? snapshot.locations?.[selectedLocation] ?? null : null}
              onClose={() => setSelectedLocation(null)}
            />
          </div>
        </main>
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

function OverallStats({ snapshot }: { snapshot: YearSnapshot | null }) {
  const result = snapshot?.simulation_result;
  const cards = [
    ["Population", snapshot?.total_population.toLocaleString() ?? "—"],
    ["Net annual change", result ? signed(result.net_change) : "—"],
    ["Births / deaths", result ? `${result.births.toLocaleString()} / ${result.deaths.toLocaleString()}` : "—"],
    ["Immigration / emigration", result ? `${result.immigration.toLocaleString()} / ${result.emigration.toLocaleString()}` : "—"],
  ];
  return (
    <div className="stats-strip">
      {cards.map(([label, value]) => (
        <div className="stat-card" key={label}>
          <div className="stat-label">{label}</div>
          <div className="stat-value">{value}</div>
        </div>
      ))}
      <div className="stat-card community-card">
        <div className="stat-label">Community background</div>
        {snapshot ? (
          <div className="community-split">
            {[
              ["Catholic", "catholic"],
              ["Protestant", "protestant"],
              ["Other", "other"],
              ["None", "none"],
            ].map(([label, key]) => (
              <span key={key}>
                <b>{label}</b>
                {percentage(snapshot.religious_breakdown[key] ?? 0, snapshot.total_population)}
              </span>
            ))}
          </div>
        ) : <div className="stat-value">—</div>}
      </div>
    </div>
  );
}

function signed(value: number) {
  return `${value >= 0 ? "+" : ""}${value.toLocaleString()}`;
}

function percentage(value: number, total: number) {
  return `${((value / Math.max(total, 1)) * 100).toFixed(1)}%`;
}
