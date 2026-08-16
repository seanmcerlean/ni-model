import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import "./app.css";
import { AboutPage } from "./components/AboutPage";
import { Controls } from "./components/Controls";
import { LocationDetail } from "./components/LocationDetail";
import { NiMap } from "./components/NiMap";
import { useSimulationStream } from "./hooks/useSimulationStream";
import { isStaticDeployment, loadRecordingManifest } from "./deployment";
import { allocateUndecided, applyPollingShock, PollingShock, UndecidedAllocation } from "./polling";
import { ChildBackgroundRule, CommunityBackground, CommunityBasis, CommunityRateAdjustments, ModelRule, PlaybackSpeed, PopulationMode, SimulationAdjustments, SimulationModel, VotingPrediction, YearSnapshot } from "./types";

const BACKGROUNDS: CommunityBackground[] = ["catholic", "protestant", "other", "none"];
type PanelTab = "setup" | "model" | "polling";
type AppPage = "simulator" | "about";
const PANEL_TABS: PanelTab[] = ["setup", "model", "polling"];

function isCommunityBackground(value: string): value is CommunityBackground {
  return BACKGROUNDS.some((background) => background === value);
}

function defaultAdjustments(): SimulationAdjustments {
  const rateDefaults = (): CommunityRateAdjustments => ({
    birth_multiplier: 1, death_multiplier: 1,
    migration_multiplier: 1, relocation_multiplier: 1,
    integration_multiplier: 1,
  });
  return {
    birth_multiplier: 1, death_multiplier: 1, migration_multiplier: 1,
    relocation_multiplier: 1, random_seed: isStaticDeployment ? null : randomSeed(),
    integration_multiplier: 1,
    community: {
      catholic: rateDefaults(), protestant: rateDefaults(),
      other: rateDefaults(), none: rateDefaults(),
    },
  };
}

function randomSeed(): number {
  const values = new Uint32Array(1);
  crypto.getRandomValues(values);
  return values[0];
}

export default function App() {
  const { snapshots, years, status, error: streamError, startStream, abort, reset } = useSimulationStream();

  const [startYear, setStartYear] = useState(2021);
  const [endYear, setEndYear] = useState(2075);
  const [currentYear, setCurrentYear] = useState<number | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [speed, setSpeed] = useState<PlaybackSpeed>(1);
  const [selectedLocation, setSelectedLocation] = useState<string | null>(null);
  const [models, setModels] = useState<SimulationModel[]>([]);
  const [recordedSeeds, setRecordedSeeds] = useState<Record<string, number>>({});
  const [modelPath, setModelPath] = useState("models/ni_current_community.yaml");
  const [modelError, setModelError] = useState<string | null>(null);
  const [voting, setVoting] = useState<VotingPrediction | null>(null);
  const [votingLoading, setVotingLoading] = useState(true);
  const [votingError, setVotingError] = useState<string | null>(null);
  const [votingCalibration, setVotingCalibration] = useState("lucidtalk_winter_2025");
  const [undecidedAllocation, setUndecidedAllocation] = useState<UndecidedAllocation>("reported");
  const [pollingShock, setPollingShock] = useState<PollingShock>("neutral");
  const [customPolling, setCustomPolling] = useState({ unite: 41.4, remain: 48.5, undecided: 10.1 });
  const [populationMode, setPopulationMode] = useState<PopulationMode>(
    isStaticDeployment ? "full" : "sample",
  );
  const [communityBasis, setCommunityBasis] = useState<CommunityBasis>("reported");
  const [adjustments, setAdjustments] = useState<SimulationAdjustments>(defaultAdjustments);
  const [panelTab, setPanelTab] = useState<PanelTab>("setup");
  const [page, setPage] = useState<AppPage>("simulator");
  const [mobileOptionsOpen, setMobileOptionsOpen] = useState(false);

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const snapshot: YearSnapshot | null =
    currentYear !== null ? (snapshots[currentYear] ?? null) : null;
  const selectedModel = models.find((model) => model.path === modelPath);
  const displayedVoting = useMemo(
    () => applyPollingShock(voting, pollingShock),
    [voting, pollingShock],
  );

  useEffect(() => {
    const modelsRequest: Promise<{
      models: SimulationModel[];
      seeds: Record<string, number>;
    }> = isStaticDeployment
      ? loadRecordingManifest().then((manifest) => ({
          models: manifest.models,
          seeds: Object.fromEntries(
            manifest.scenarios.map((scenario) => [scenario.model_path, scenario.seed]),
          ),
        }))
      : fetch("/api/simulation/models").then((response) => {
          if (!response.ok) throw new Error("Could not load model definitions.");
          return response.json().then((models: SimulationModel[]) => ({
            models,
            seeds: {},
          }));
        });
    modelsRequest
      .then(({ models: availableModels, seeds }) => {
        setModels(availableModels);
        setRecordedSeeds(seeds);
        if (isStaticDeployment) {
          const seed = seeds[modelPath];
          if (seed !== undefined) {
            setAdjustments((current) => ({
              ...current,
              random_seed: seed,
            }));
          }
        }
        setModelError(null);
      })
      .catch(() => {
        setModels([]);
        setModelError(
          isStaticDeployment
            ? "Could not load the recorded model catalogue."
            : "Could not load model definitions from the local API.",
        );
      });
  }, []);

  useEffect(() => {
    const isCustom = votingCalibration === "custom_lucidtalk";
    const customTotal = customPolling.unite + customPolling.remain + customPolling.undecided;
    if (isCustom && Math.abs(customTotal - 100) > 0.01) {
      setVotingError(`Custom baseline totals ${customTotal.toFixed(1)}%; it must total 100%.`);
      setVotingLoading(false);
      return;
    }

    if (isStaticDeployment) {
      const key = `${votingCalibration}:${communityBasis}`;
      const prediction = snapshot?.voting_predictions?.[key]
        ?? snapshot?.voting_predictions?.[votingCalibration]
        ?? null;
      setVoting(prediction);
      setVotingLoading(false);
      setVotingError(
        prediction || snapshot === null ? null : "This recording has no matching polling estimate.",
      );
      return;
    }

    const controller = new AbortController();
    setVotingLoading(true);
    setVotingError(null);
    const params = new URLSearchParams({
      calibration: isCustom ? "lucidtalk_winter_2025" : votingCalibration,
      include_locations: "true",
      community_basis: communityBasis,
    });
    if (isCustom) {
      params.set("custom_unite", String(customPolling.unite));
      params.set("custom_remain", String(customPolling.remain));
      params.set("custom_undecided", String(customPolling.undecided));
    }
    const endpoint = snapshot?.run_id
      ? `/api/simulation/runs/${snapshot.run_id}/years/${snapshot.year}/voting-prediction?${params}`
      : `/api/population/voting-prediction?${params}`;
    fetch(endpoint, { signal: controller.signal })
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
  }, [snapshot, votingCalibration, customPolling, communityBasis]);

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
    setMobileOptionsOpen(false);
    startStream(startYear, endYear, modelPath, adjustments, populationMode);
  }, [startYear, endYear, modelPath, adjustments, populationMode, startStream]);

  const handlePlayPause = useCallback(() => {
    setIsPlaying((p) => !p);
  }, []);

  const handleModelChange = useCallback((path: string) => {
    reset();
    setModelPath(path);
    const model = models.find((item) => item.path === path);
    if (model?.default_start_year) setStartYear(model.default_start_year);
    if (model?.default_end_year) setEndYear(model.default_end_year);
    const recordedSeed = recordedSeeds[path];
    if (isStaticDeployment && recordedSeed !== undefined) {
      setAdjustments((current) => ({ ...current, random_seed: recordedSeed }));
    }
    setCurrentYear(null);
    setIsPlaying(false);
  }, [models, recordedSeeds, reset]);

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
        <div className="header-actions">
          {page === "simulator" && (
            <button
              type="button"
              className="mobile-panel-toggle"
              aria-controls="simulation-options"
              aria-expanded={mobileOptionsOpen}
              onClick={() => setMobileOptionsOpen((open) => !open)}
            >
              {mobileOptionsOpen ? "View map" : "Options"}
            </button>
          )}
          <nav className="primary-navigation" aria-label="Primary navigation">
            <button type="button" aria-current={page === "simulator" ? "page" : undefined}
              onClick={() => setPage("simulator")}>Simulator</button>
            <button type="button" aria-current={page === "about" ? "page" : undefined}
              onClick={() => setPage("about")}>About</button>
          </nav>
          {status === "streaming" && (
            <button className="stop-button" onClick={abort}>Stop simulation</button>
          )}
        </div>
      </header>

      {page === "about" ? <AboutPage /> : <>
      <div className="workspace">
        <aside
          className={`model-panel${mobileOptionsOpen ? " mobile-panel-open" : ""}`}
          id="simulation-options"
        >
          <div className="panel-kicker">MODEL</div>
          <label className="field-label" htmlFor="model-select">Scenario definition</label>
          <select
            id="model-select"
            className="model-select"
            value={modelPath}
            disabled={models.length === 0}
            onChange={(event) => handleModelChange(event.target.value)}
          >
            {models.length === 0 && <option value={modelPath}>NI Current Community Model</option>}
            {models.map((model) => <option key={model.id} value={model.path}>{model.name}</option>)}
          </select>
          {modelError && <p className="inline-error" role="alert">{modelError}</p>}
          <div className="panel-tabs" role="tablist" aria-label="Simulation options">
            <PanelTabButton id="setup" label="Run setup" selected={panelTab} onSelect={setPanelTab} />
            <PanelTabButton id="model" label="Model info" selected={panelTab} onSelect={setPanelTab} />
            <PanelTabButton id="polling" label="Polling" selected={panelTab} onSelect={setPanelTab} />
          </div>
          {panelTab === "setup" && (
            <section className="panel-tab-content" role="tabpanel" id="setup-panel" aria-labelledby="setup-tab">
              <p className="panel-intro">Choose the population size and assumptions for the next run.</p>
              {isStaticDeployment && <p className="model-note">Recorded full-population run. Demographic assumptions and the model-specific seed are fixed.</p>}
              <label className="population-toggle">
                <span><b>Full population</b><small>{populationMode === "full" ? "Every resident in the selected baseline" : "Off — representative 25,000-person sample"}</small></span>
                <input type="checkbox" role="switch" checked={populationMode === "full"}
                  disabled={status === "streaming" || isStaticDeployment}
                  onChange={(event) => setPopulationMode(event.target.checked ? "full" : "sample")} />
              </label>
              <div className="seed-control">
                <label htmlFor="random-seed">Simulation seed</label>
                {isStaticDeployment ? (
                  <input id="random-seed" type="number" disabled value={adjustments.random_seed ?? ""} />
                ) : <>
                  <input id="random-seed" type="number" min="0" max="4294967295"
                    disabled={status === "streaming"} value={adjustments.random_seed ?? ""}
                    onChange={(event) => setAdjustments({
                      ...adjustments,
                      random_seed: event.target.value === "" ? null : Number(event.target.value),
                    })} />
                  <button type="button" className="control-button" disabled={status === "streaming"}
                    onClick={() => setAdjustments({ ...adjustments, random_seed: randomSeed() })}>New seed</button>
                </>}
              </div>
              <AdjustmentEditor value={adjustments} onChange={setAdjustments} disabled={status === "streaming" || isStaticDeployment} />
            </section>
          )}
          {panelTab === "model" && (
            <section className="panel-tab-content" role="tabpanel" id="model-panel" aria-labelledby="model-tab">
              {!selectedModel && <p className="panel-intro">Model details are loading from the API.</p>}
              {selectedModel && <>
              <p className="model-description">{selectedModel.description}</p>
              <dl className="model-facts">
                <div><dt>Seed</dt><dd>{selectedModel.random_seed ?? "Random"}</dd></div>
                <div><dt>Rate jitter</dt><dd>±{(selectedModel.rate_jitter * 100).toFixed(0)}%</dd></div>
                {selectedModel.baseline_year && <div><dt>Baseline year</dt><dd>{selectedModel.baseline_year}</dd></div>}
                <div><dt>Baseline population</dt><dd>{selectedModel.baseline_population?.toLocaleString() ?? "Unknown"}</dd></div>
                {selectedModel.data_through && <div><dt>Observed through</dt><dd>{selectedModel.data_through}</dd></div>}
                {selectedModel.projection_version && <div><dt>Projection</dt><dd>{selectedModel.projection_version}</dd></div>}
              </dl>
              <div className="rule-groups">
                <RuleGroup title="Birth rules" rules={selectedModel.birth_rate_rules} />
                <RuleGroup title="Mortality rules" rules={selectedModel.death_rate_rules} />
                {selectedModel.mortality_age_rates?.length ? (
                  <RuleGroup
                    title="Mortality age profile"
                    rules={selectedModel.mortality_age_rates}
                  />
                ) : null}
                <RuleGroup
                  title="Migration rules"
                  rules={[
                    ...selectedModel.migration_rate_rules,
                    ...selectedModel.internal_migration_rate_rules,
                  ]}
                />
                <RuleGroup
                  title="Community integration rules"
                  rules={selectedModel.integration_rate_rules ?? []}
                />
                <ChildRuleGroup
                  title="Newborn background rules"
                  rules={selectedModel.child_background_rule_details ?? []}
                />
              </div>
              <div className="model-note">Rates are scenario assumptions per 1,000, not an official forecast.</div>
              </>}
            </section>
          )}
          {panelTab === "polling" && (
            <div className="panel-tab-content" role="tabpanel" id="polling-panel" aria-labelledby="polling-tab">
              <label className="population-toggle">
                <span><b>Probable community</b><small>{communityBasis === "probable" ? "Estimated Catholic / Protestant / Other lineage" : "Off — Census reported background"}</small></span>
                <input type="checkbox" role="switch" checked={communityBasis === "probable"}
                  onChange={(event) => setCommunityBasis(event.target.checked ? "probable" : "reported")} />
              </label>
              <VotingPanel prediction={displayedVoting} calibration={votingCalibration}
                customPolling={customPolling} onCustomPollingChange={setCustomPolling}
                loading={votingLoading} error={votingError}
                pollingShock={pollingShock} onPollingShockChange={setPollingShock}
                undecidedAllocation={undecidedAllocation}
                onUndecidedAllocationChange={setUndecidedAllocation}
                onCalibrationChange={setVotingCalibration} />
            </div>
          )}
        </aside>

        <main className="map-column">
          <OverallStats snapshot={snapshot} communityBasis={communityBasis} />
          <div className="map-frame">
            <NiMap snapshot={snapshot} voting={displayedVoting} communityBasis={communityBasis} onLocationClick={setSelectedLocation} />
            <LocationDetail
              locationId={selectedLocation}
              year={currentYear}
              detail={selectedLocation && snapshot ? snapshot.locations?.[selectedLocation] ?? null : null}
              voting={selectedLocation ? displayedVoting?.by_location?.[selectedLocation] ?? null : null}
              pollingSource={displayedVoting?.source.name ?? null}
              undecidedAllocation={undecidedAllocation}
              communityBasis={communityBasis}
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
        canRun={models.length > 0 && startYear <= endYear
          && endYear <= (selectedModel?.default_end_year ?? endYear)
          && (!isStaticDeployment || adjustments.random_seed !== null)
          && status !== "streaming"}
        startYearLocked
        endYearLocked={isStaticDeployment}
        endYearMax={selectedModel?.default_end_year ?? 2200}
        onStartStream={handleStartStream}
        onPlayPause={handlePlayPause}
        onSpeedChange={setSpeed}
        onScrub={handleScrub}
        onStartYearChange={setStartYear}
        onEndYearChange={setEndYear}
      />
      </>}
    </div>
  );
}

function PanelTabButton({ id, label, selected, onSelect }: {
  id: PanelTab;
  label: string;
  selected: PanelTab;
  onSelect: (tab: PanelTab) => void;
}) {
  const active = selected === id;
  const moveFocus = (tab: PanelTab) => {
    onSelect(tab);
    document.getElementById(`${tab}-tab`)?.focus();
  };
  return (
    <button type="button" role="tab" id={`${id}-tab`} aria-controls={`${id}-panel`}
      aria-selected={active} tabIndex={active ? 0 : -1}
      onKeyDown={(event) => {
        const index = PANEL_TABS.indexOf(id);
        if (event.key === "ArrowRight") {
          event.preventDefault();
          moveFocus(PANEL_TABS[(index + 1) % PANEL_TABS.length]);
        } else if (event.key === "ArrowLeft") {
          event.preventDefault();
          moveFocus(PANEL_TABS[(index - 1 + PANEL_TABS.length) % PANEL_TABS.length]);
        } else if (event.key === "Home") {
          event.preventDefault();
          moveFocus(PANEL_TABS[0]);
        } else if (event.key === "End") {
          event.preventDefault();
          moveFocus(PANEL_TABS[PANEL_TABS.length - 1]);
        }
      }}
      onClick={() => onSelect(id)}>{label}</button>
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
    ["integration_multiplier", "Community integration"],
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
    <button type="button" className="control-button" disabled={disabled}
      onClick={() => onChange(defaultAdjustments())}>Reset</button>
  </details>;
}

function VotingPanel({ prediction, calibration, customPolling, loading, error, pollingShock, undecidedAllocation, onCalibrationChange, onCustomPollingChange, onPollingShockChange, onUndecidedAllocationChange }: {
  prediction: VotingPrediction | null;
  calibration: string;
  customPolling: { unite: number; remain: number; undecided: number };
  loading: boolean;
  error: string | null;
  pollingShock: PollingShock;
  undecidedAllocation: UndecidedAllocation;
  onCalibrationChange: (value: string) => void;
  onCustomPollingChange: (value: { unite: number; remain: number; undecided: number }) => void;
  onPollingShockChange: (value: PollingShock) => void;
  onUndecidedAllocationChange: (value: UndecidedAllocation) => void;
}) {
  if (!prediction) return (
    <section className="voting-panel" aria-labelledby="voting-heading">
      <div className="panel-kicker" id="voting-heading">BORDER POLL SCENARIO</div>
      <p className="panel-intro" aria-live="polite">
        {error ?? (loading ? "Loading polling calibration…" : "No polling estimate is available.")}
      </p>
    </section>
  );
  const interval = prediction.intervals.unite_share;
  const displayed = allocateUndecided(prediction, undecidedAllocation);
  return (
    <section className="voting-panel" aria-labelledby="voting-heading">
      <div className="panel-kicker" id="voting-heading">BORDER POLL SCENARIO</div>
      <div className="voting-headline" aria-live="polite">
        <span><b>{percentage(displayed.unite_share, 1)}</b> Unite</span>
        <span><b>{percentage(displayed.remain_share, 1)}</b> Remain</span>
        <span><b>{percentage(displayed.undecided_share, 1)}</b> Undecided</span>
      </div>
      <label className="field-label" htmlFor="voting-calibration">Polling calibration</label>
      <select id="voting-calibration" className="model-select" value={calibration}
        onChange={(event) => onCalibrationChange(event.target.value)}>
        <option value="lucidtalk_winter_2025">LucidTalk Winter 2025</option>
        <option value="lucidtalk_summer_2021_high">LucidTalk Aug 2021 — five-year high</option>
        <option value="lucidtalk_winter_2024_low">LucidTalk Feb 2024 — five-year low</option>
        <option value="nilt_2024">NILT 2024</option>
        {!isStaticDeployment && <option value="custom_lucidtalk">Custom baseline (LucidTalk-relative)</option>}
      </select>
      {calibration === "custom_lucidtalk" && (
        <><fieldset className="custom-polling" aria-label="Custom polling baseline">
          {(["unite", "remain", "undecided"] as const).map((key) => (
            <label key={key}>
              <span>{friendly(key)} %</span>
              <input type="number" min="0" max="100" step="0.1"
                value={customPolling[key]}
                onChange={(event) => onCustomPollingChange({
                  ...customPolling, [key]: Number(event.target.value),
                })} />
            </label>
          ))}
        </fieldset>
        <p className="custom-polling-note">This is the present-day baseline. Projected figures update as each simulation year's demographics change.</p></>
      )}
      <div className="calibration-status">Showing {prediction.source.name}</div>
      {error && <p className="inline-error" role="alert">{error}</p>}
      <fieldset className="undecided-allocation polling-shock">
        <legend>Polling shock</legend>
        {([
          ["neutral", "Neutral"],
          ["brexit", "Brexit"],
          ["anti_brexit", "Anti-Brexit"],
        ] as Array<[PollingShock, string]>).map(([value, label]) => (
          <label key={value}>
            <input type="radio" name="polling-shock" value={value}
              checked={pollingShock === value}
              onChange={() => onPollingShockChange(value)} />
            {label}
          </label>
        ))}
      </fieldset>
      <p className="custom-polling-note">
        Brexit transfers 4.6 points toward Unite, matching the 2015–2016 NILT change in long-term unity preference. Anti-Brexit is the symmetric counterfactual. Undecided is unchanged.
      </p>
      <fieldset className="undecided-allocation">
        <legend>Undecided treatment</legend>
        {([
          ["reported", "All respondents"],
          ["decided", "Decided voters (headline)"],
        ] as Array<[UndecidedAllocation, string]>).map(([value, label]) => (
          <label key={value}>
            <input type="radio" name="undecided-allocation" value={value}
              checked={undecidedAllocation === value}
              onChange={() => onUndecidedAllocationChange(value)} />
            {label}
          </label>
        ))}
      </fieldset>
      <p className="allocation-note">
        The headline view excludes undecided respondents and renormalises Unite and Remain to 100%; it does not predict how undecided people will vote.
      </p>
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
        <a href={prediction.source.url} target="_blank" rel="noreferrer">{prediction.source.name}</a>, n={prediction.source.sample_size}. {prediction.source.community_basis === "probable" ? "Probable community is an ecological estimate used to select poll cross-tabs, not a vote." : "Community background is a polling calibration, not a vote."}
      </p>
    </section>
  );
}

function OverallStats({ snapshot, communityBasis }: { snapshot: YearSnapshot | null; communityBasis: CommunityBasis }) {
  const result = snapshot?.simulation_result;
  const cards = [
    ["Population", snapshot?.total_population.toLocaleString() ?? "—"],
    ["Net annual change", result ? signed(result.net_change) : "—"],
    ["Births / deaths", result ? `${result.births.toLocaleString()} / ${result.deaths.toLocaleString()}` : "—"],
    ["Immigration / emigration", result ? `${result.immigration.toLocaleString()} / ${result.emigration.toLocaleString()}` : "—"],
    ["Community transitions", result ? (result.community_transitions ?? 0).toLocaleString() : "—"],
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
        <div className="stat-label">{communityBasis === "probable" ? "Probable community (estimate)" : "Census community background"}</div>
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
                {percentage((communityBasis === "probable" ? snapshot.probable_community_breakdown ?? {} : snapshot.religious_breakdown)[key] ?? 0, snapshot.total_population)}
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
              {rule.age_min !== undefined && rule.age_max !== undefined && (
                <span>Age: <b>{rule.age_min === rule.age_max ? rule.age_min : `${rule.age_min}–${rule.age_max}`}</b></span>
              )}
              {rule.destination && <span>Destination: <b>{friendly(rule.destination)}</b></span>}
              {rule.flow && <span>Flow: <b>{friendly(rule.flow)}</b></span>}
              {rule.evidence && <span>Evidence: <b>{friendly(rule.evidence)}</b></span>}
              {Object.keys(rule.filters ?? {}).length === 0 && rule.age_min === undefined && !rule.destination && <span>Whole population</span>}
            </div>
          </div>
        ))}
      </div>
    </details>
  );
}

function ChildRuleGroup({ title, rules }: { title: string; rules: ChildBackgroundRule[] }) {
  return (
    <details className="rule-group">
      <summary><span>{title}</span><b>{rules.length}</b></summary>
      <div className="rule-list">
        {rules.length === 0 && <div className="empty-rules">No active rules</div>}
        {rules.map((rule, index) => (
          <div className="rule-item" key={`${title}-${index}`}>
            <div className="rule-heading">
              <strong>{friendly(rule.source)} parent proxy</strong>
              <span>{yearRange(rule)}</span>
            </div>
            <div className="rule-filters">
              {Object.entries(rule.probabilities).map(([background, probability]) => (
                <span key={background}>{friendly(background)}: <b>{(probability * 100).toFixed(1)}%</b></span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </details>
  );
}

function yearRange(rule: Pick<ModelRule, "year_min" | "year_max">) {
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
