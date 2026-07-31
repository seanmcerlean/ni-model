import { useCallback, useEffect, useRef, useState } from "react";

import "./app.css";
import { Controls } from "./components/Controls";
import { LocationDetail } from "./components/LocationDetail";
import { NiMap } from "./components/NiMap";
import { useSimulationStream } from "./hooks/useSimulationStream";
import { CommunityBackground, CommunityRateAdjustments, ModelRule, PlaybackSpeed, SimulationAdjustments, SimulationModel, VotingPrediction, YearSnapshot } from "./types";

const BACKGROUNDS: CommunityBackground[] = ["catholic", "protestant", "other", "none"];

function isCommunityBackground(value: string): value is CommunityBackground {
  return BACKGROUNDS.some((background) => background === value);
}

function defaultAdjustments(): SimulationAdjustments {
  const rateDefaults = (): CommunityRateAdjustments => ({
    birth_multiplier: 1, death_multiplier: 1,
    migration_multiplier: 1, relocation_multiplier: 1,
  });
  return {
    birth_multiplier: 1, death_multiplier: 1, migration_multiplier: 1,
    relocation_multiplier: 1, random_seed: null,
    community: {
      catholic: rateDefaults(), protestant: rateDefaults(),
      other: rateDefaults(), none: rateDefaults(),
    },
  };
}

export default function App() {
  const { snapshots, years, status, error: streamError, startStream, abort } = useSimulationStream();

  const [startYear, setStartYear] = useState(2024);
  const [endYear, setEndYear] = useState(2035);
  const [currentYear, setCurrentYear] = useState<number | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [speed, setSpeed] = useState<PlaybackSpeed>(1);
  const [selectedLocation, setSelectedLocation] = useState<string | null>(null);
  const [models, setModels] = useState<SimulationModel[]>([]);
  const [modelPath, setModelPath] = useState("models/ni_current.yaml");
  const [modelError, setModelError] = useState<string | null>(null);
  const [voting, setVoting] = useState<VotingPrediction | null>(null);
  const [votingLoading, setVotingLoading] = useState(true);
  const [votingError, setVotingError] = useState<string | null>(null);
  const [votingCalibration, setVotingCalibration] = useState("lucidtalk_winter_2025");
  const [adjustments, setAdjustments] = useState<SimulationAdjustments>(defaultAdjustments);

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const snapshot: YearSnapshot | null =
    currentYear !== null ? (snapshots[currentYear] ?? null) : null;
  const selectedModel = models.find((model) => model.path === modelPath);

  useEffect(() => {
    fetch("/api/simulation/models")
      .then((response) => {
        if (!response.ok) throw new Error("Could not load model definitions.");
        return response.json();
      })
      .then((availableModels: SimulationModel[]) => {
        setModels(availableModels);
        setModelError(null);
      })
      .catch(() => {
        setModels([]);
        setModelError("Could not load model definitions from the local API.");
      });
  }, []);

  useEffect(() => {
    const simulatedPrediction = snapshot?.voting_predictions?.[votingCalibration];
    if (simulatedPrediction) {
      setVoting(simulatedPrediction);
      setVotingLoading(false);
      setVotingError(null);
      return;
    }

    const controller = new AbortController();
    setVotingLoading(true);
    setVotingError(null);
    const params = new URLSearchParams({
      calibration: votingCalibration,
      include_locations: "false",
    });
    if (snapshot?.run_id) params.set("run_id", snapshot.run_id);
    fetch(`/api/population/voting-prediction?${params}`, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error("Voting scenario unavailable");
        return response.json();
      })
      .then((prediction: VotingPrediction) => {
        setVoting(prediction);
        setVotingLoading(false);
      })
      .catch((error: Error) => {
        if (error.name !== "AbortError") {
          setVotingError("Could not update the voting calibration.");
          setVotingLoading(false);
        }
      });
    return () => controller.abort();
  }, [snapshot, votingCalibration]);

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
    startStream(startYear, endYear, modelPath, adjustments);
  }, [startYear, endYear, modelPath, adjustments, startStream]);

  const handlePlayPause = useCallback(() => {
    setIsPlaying((p) => !p);
  }, []);

  const handleModelChange = useCallback((path: string) => {
    setModelPath(path);
    const model = models.find((item) => item.path === path);
    if (model?.default_start_year) setStartYear(model.default_start_year);
    if (model?.default_end_year) setEndYear(model.default_end_year);
    setCurrentYear(null);
    setIsPlaying(false);
  }, [models]);

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
            onChange={(event) => handleModelChange(event.target.value)}
          >
            {models.length === 0 && <option value={modelPath}>NI Current Model</option>}
            {models.map((model) => <option key={model.id} value={model.path}>{model.name}</option>)}
          </select>
          {modelError && <p className="inline-error" role="alert">{modelError}</p>}
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
              <AdjustmentEditor value={adjustments} onChange={setAdjustments} disabled={status === "streaming"} />
            </>
          )}
          <VotingPanel prediction={voting} calibration={votingCalibration}
            loading={votingLoading} error={votingError}
            projectionYear={snapshot?.year ?? null}
            onCalibrationChange={setVotingCalibration} />
        </aside>

        <main className="map-column">
          <OverallStats snapshot={snapshot} />
          <div className="map-frame">
            <NiMap snapshot={snapshot} onLocationClick={setSelectedLocation} />
            <LocationDetail
              locationId={selectedLocation}
              year={currentYear}
              detail={selectedLocation && snapshot ? snapshot.locations?.[selectedLocation] ?? null : null}
              voting={selectedLocation ? voting?.by_location?.[selectedLocation] ?? null : null}
              pollingSource={voting?.source.name ?? null}
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
        error={streamError}
        canRun={startYear <= endYear && status !== "streaming"}
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

function AdjustmentEditor({ value, onChange, disabled }: {
  value: SimulationAdjustments;
  onChange: (value: SimulationAdjustments) => void;
  disabled: boolean;
}) {
  const [selectedBackground, setSelectedBackground] = useState<CommunityBackground>("catholic");
  const fields: Array<[keyof CommunityRateAdjustments, string]> = [
    ["birth_multiplier", "Birth rates"], ["death_multiplier", "Mortality rates"],
    ["migration_multiplier", "External migration"], ["relocation_multiplier", "Internal relocation"],
  ];
  return <details className="adjustment-editor">
    <summary>Adjust this run</summary>
    <p>Multipliers apply to every matching source-model rule. 1.00 keeps the published value.</p>
    {fields.map(([key, label]) => <label key={key}>{label}
      <input type="number" min="0" max="3" step="0.05" disabled={disabled}
        value={value[key] ?? ""}
        onChange={(event) => onChange({ ...value, [key]: Number(event.target.value) })} />
    </label>)}
    <fieldset className="community-adjustments">
      <legend>Community-specific multipliers</legend>
      <label className="community-selector">Background
        <select value={selectedBackground} disabled={disabled}
          onChange={(event) => {
            if (isCommunityBackground(event.target.value)) setSelectedBackground(event.target.value);
          }}>
          {BACKGROUNDS.map((background) => <option key={background} value={background}>{friendly(background)}</option>)}
        </select>
      </label>
      <div className="community-rate-fields">
        {fields.map(([key, label]) => <label key={key}>{label}
          <input type="number" min="0" max="3" step="0.05" disabled={disabled}
            value={value.community[selectedBackground][key]}
            onChange={(event) => onChange({
              ...value,
              community: {
                ...value.community,
                [selectedBackground]: {
                  ...value.community[selectedBackground], [key]: Number(event.target.value),
                },
              },
            })} />
        </label>)}
      </div>
    </fieldset>
    <label>Random seed<input type="number" disabled={disabled} placeholder="Model default"
      value={value.random_seed ?? ""}
      onChange={(event) => onChange({ ...value, random_seed: event.target.value === "" ? null : Number(event.target.value) })} /></label>
    <button type="button" className="control-button" disabled={disabled}
      onClick={() => onChange(defaultAdjustments())}>Reset</button>
  </details>;
}

function VotingPanel({ prediction, calibration, loading, error, projectionYear, onCalibrationChange }: {
  prediction: VotingPrediction | null;
  calibration: string;
  loading: boolean;
  error: string | null;
  projectionYear: number | null;
  onCalibrationChange: (value: string) => void;
}) {
  if (!prediction) return null;
  const interval = prediction.intervals.unite_share;
  return (
    <section className="voting-panel" aria-labelledby="voting-heading">
      <div className="panel-kicker" id="voting-heading">BORDER POLL SCENARIO</div>
      <label className="field-label" htmlFor="voting-calibration">Polling calibration</label>
      <select id="voting-calibration" className="model-select" value={calibration}
        onChange={(event) => onCalibrationChange(event.target.value)}>
        <option value="lucidtalk_winter_2025">LucidTalk Winter 2025</option>
        <option value="nilt_2024">NILT 2024</option>
      </select>
      <div className={`calibration-status ${loading ? "loading" : ""}`} aria-live="polite">
        {loading ? "Updating calibration…" : `Showing ${prediction.source.name}`}
      </div>
      {error && <p className="inline-error" role="alert">{error}</p>}
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
        <a href={prediction.source.url} target="_blank" rel="noreferrer">{prediction.source.name}</a>, n={prediction.source.sample_size}. Community background is a polling calibration, not a vote.
        {projectionYear !== null && <> Estimate recalculated from the simulated {projectionYear} adult population.</>}
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
