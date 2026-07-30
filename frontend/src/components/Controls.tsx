import { PlaybackSpeed, StreamStatus } from "../types";

interface Props {
  status: StreamStatus;
  years: number[];
  currentYear: number | null;
  isPlaying: boolean;
  speed: PlaybackSpeed;
  startYear: number;
  endYear: number;
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
        <label className="control-label">Start</label>
        <input
          type="number"
          value={startYear}
          min={1900}
          max={2200}
          className="year-input"
          onChange={(e) => onStartYearChange(Number(e.target.value))}
        />
        <label className="control-label">End</label>
        <input
          type="number"
          value={endYear}
          min={1900}
          max={2200}
          className="year-input"
          onChange={(e) => onEndYearChange(Number(e.target.value))}
        />
        <button className="primary-button" onClick={onStartStream} disabled={status === "streaming"}>
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
            onClick={() => onSpeedChange(s)}
          >
            {s}×
          </button>
        ))}
      </div>

      <div className="scrub-row">
        <input
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
      {status === "error" && (
        <div className="stream-error">Stream error — check the local API.</div>
      )}
    </div>
  );
}
