import { useCallback, useEffect, useRef, useState } from "react";

import "./app.css";
import { Controls } from "./components/Controls";
import { LocationDetail } from "./components/LocationDetail";
import { NiMap } from "./components/NiMap";
import { useSimulationStream } from "./hooks/useSimulationStream";
import { ModelRule, PlaybackSpeed, SimulationModel, VotingPrediction, YearSnapshot } from "./types";

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
  const [voting, setVoting] = useState<VotingPrediction | null>(null);

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

  useEffect(() => {
    const controller = new AbortController();
    const runQuery = snapshot?.run_id ? `?run_id=${snapshot.run_id}` : "";
    fetch(`/api/population/voting-prediction${runQuery}`, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error("Voting scenario unavailable");
        return response.json();
      })
      .then((prediction: VotingPrediction) => setVoting(prediction))
      .catch((error: Error) => {
        if (error.name !== "AbortError") setVoting(null);
      });
    return () => controller.abort();
  }, [snapshot?.run_id]);

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
                {selectedModel.baseline_year && <div><dt>Baseline</dt><dd>{selectedModel.baseline_year} Census</dd></div>}
                {selectedModel.data_through && <div><dt>Observed through</dt><dd>{selectedModel.data_through}</dd></div>}
                {selectedModel.projection_version && <div><dt>Projection</dt><dd>{selectedModel.projection_version}</dd></div>}
              </dl>
              <div className="rule-groups">
                <RuleGroup title="Birth rules" rules={selectedModel.birth_rate_rules} />
                <RuleGroup title="Mortality rules" rules={selectedModel.death_rate_rules} />
                <RuleGroup
                  title="Migration rules"
                  rules={[
                    ...selectedModel.migration_rate_rules,
                    ...selectedModel.internal_migration_rate_rules,
                  ]}
                />
              </div>
              <div className="model-note">Rates are scenario assumptions per 1,000, not an official forecast.</div>
            </>
          )}
          <VotingPanel prediction={voting} />
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

function VotingPanel({ prediction }: { prediction: VotingPrediction | null }) {
  if (!prediction) return null;
  const interval = prediction.intervals.unite_share;
  return (
    <section className="voting-panel" aria-labelledby="voting-heading">
      <div className="panel-kicker" id="voting-heading">BORDER POLL SCENARIO</div>
      <div className="voting-headline">
        <span><b>{percentage(prediction.unite_share, 1)}</b> Unite</span>
        <span><b>{percentage(prediction.remain_share, 1)}</b> Remain</span>
        <span><b>{percentage(prediction.undecided_share, 1)}</b> Undecided</span>
      </div>
      <dl className="model-facts">
        <div><dt>Adult proxy</dt><dd>{prediction.eligible_population.toLocaleString()}</dd></div>
        <div><dt>Projected turnout</dt><dd>{percentage(prediction.turnout_rate, 1)}</dd></div>
        <div><dt>Unity survey interval</dt><dd>{percentage(interval.low, 1)}–{percentage(interval.high, 1)}</dd></div>
      </dl>
      <details className="rule-group">
        <summary><span>Undecided sensitivity</span><b>3</b></summary>
        <div className="scenario-list">
          {prediction.scenarios.map((scenario) => (
            <div key={scenario.id}><span>{scenario.label}</span><b>{percentage(scenario.unite_share, 1)}</b></div>
          ))}
        </div>
      </details>
      <p className="voting-source">
        <a href={prediction.source.url} target="_blank" rel="noreferrer">NILT 2024</a>, n={prediction.source.sample_size}. Community background is a polling calibration, not a vote.
      </p>
    </section>
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

function RuleGroup({ title, rules }: { title: string; rules: ModelRule[] }) {
  return (
    <details className="rule-group">
      <summary><span>{title}</span><b>{rules.length}</b></summary>
      <div className="rule-list">
        {rules.length === 0 && <div className="empty-rules">No active rules</div>}
        {rules.map((rule, index) => (
          <div className="rule-item" key={`${title}-${index}`}>
            <div className="rule-heading">
              <strong>{rule.rate} per 1,000</strong>
              <span>{yearRange(rule)}</span>
            </div>
            <div className="rule-filters">
              {Object.entries(rule.filters ?? {}).map(([key, value]) => (
                <span key={key}>{friendly(key)}: <b>{friendly(String(value))}</b></span>
              ))}
              {rule.destination && <span>Destination: <b>{friendly(rule.destination)}</b></span>}
              {rule.flow && <span>Flow: <b>{friendly(rule.flow)}</b></span>}
              {rule.evidence && <span>Evidence: <b>{friendly(rule.evidence)}</b></span>}
              {Object.keys(rule.filters ?? {}).length === 0 && !rule.destination && <span>Whole population</span>}
            </div>
          </div>
        ))}
      </div>
    </details>
  );
}

function yearRange(rule: ModelRule) {
  if (rule.year_min && rule.year_max) return `${rule.year_min}–${rule.year_max}`;
  if (rule.year_min) return `${rule.year_min}+`;
  if (rule.year_max) return `to ${rule.year_max}`;
  return "All years";
}

function friendly(value: string) {
  return value
    .toLowerCase()
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter: string) => letter.toUpperCase());
}
