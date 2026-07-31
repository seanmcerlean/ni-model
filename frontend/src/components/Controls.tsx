import { PlaybackSpeed, StreamStatus } from "../types";

interface Props {
  status: StreamStatus;
  years: number[];
  currentYear: number | null;
  isPlaying: boolean;
  speed: PlaybackSpeed;
  startYear: number;
  endYear: number;
  error?: string | null;
  canRun?: boolean;
  onStartStream: () => void;
  onPlayPause: () => void;
  onSpeedChange: (s: PlaybackSpeed) => void;
  onScrub: (year: number) => void;
  onStartYearChange: (y: number) => void;
  onEndYearChange: (y: number) => void;
}

const SPEEDS: PlaybackSpeed[] = [0.5, 1, 2, 5];

export function Controls({
  status,
  years,
  currentYear,
  isPlaying,
  speed,
  startYear,
  endYear,
  error = null,
  canRun = true,
  onStartStream,
  onPlayPause,
  onSpeedChange,
  onScrub,
  onStartYearChange,
  onEndYearChange,
}: Props) {
  const buffered = years.length;
  const total = endYear - startYear + 1;
  const scrubMax = years.length > 0 ? years[years.length - 1] : startYear;
  const scrubMin = years.length > 0 ? years[0] : startYear;

  return (
    <div className="controls">
      <div className="control-row">
        <label className="control-label" htmlFor="start-year">Start</label>
        <input
          id="start-year"
          type="number"
          value={startYear}
          min={1900}
          max={2200}
          className="year-input"
          onChange={(e) => onStartYearChange(Number(e.target.value))}
        />
        <label className="control-label" htmlFor="end-year">End</label>
        <input
          id="end-year"
          type="number"
          value={endYear}
          min={1900}
          max={2200}
          className="year-input"
          onChange={(e) => onEndYearChange(Number(e.target.value))}
        />
        <button className="primary-button" onClick={onStartStream} disabled={status === "streaming" || !canRun}>
          {status === "streaming" ? "Streaming…" : "Run"}
        </button>
      </div>

      <div className="control-row playback-row">
        <button
          className="control-button"
          onClick={onPlayPause}
          disabled={years.length === 0}
        >
          {isPlaying ? "⏸ Pause" : "▶ Play"}
        </button>
        <span className="current-year">
          {currentYear ?? "—"}
        </span>
        <span className="control-label">Speed</span>
        {SPEEDS.map((s) => (
          <button
            key={s}
            className={`control-button ${speed === s ? "active" : ""}`}
            aria-pressed={speed === s}
            onClick={() => onSpeedChange(s)}
          >
            {s}×
          </button>
        ))}
      </div>

      <div className="scrub-row">
        <label className="sr-only" htmlFor="simulation-year">Simulation year</label>
        <input
          id="simulation-year"
          type="range"
          min={scrubMin}
          max={scrubMax}
          value={currentYear ?? scrubMin}
          disabled={years.length === 0}
          onChange={(e) => onScrub(Number(e.target.value))}
        />
      </div>

      <div className="progress-bar">
        <div
          className="progress-fill"
          style={{ width: `${total > 0 ? (buffered / total) * 100 : 0}%` }}
        />
      </div>
      {(error || status === "error") && (
        <div className="stream-error" role="alert">{error ?? "Stream error — check the local API."}</div>
      )}
    </div>
  );
}
