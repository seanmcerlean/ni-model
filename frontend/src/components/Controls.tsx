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
    <div style={styles.panel}>
      <div style={styles.row}>
        <label style={styles.label}>Start</label>
        <input
          type="number"
          value={startYear}
          min={1900}
          max={2200}
          style={styles.yearInput}
          onChange={(e) => onStartYearChange(Number(e.target.value))}
        />
        <label style={styles.label}>End</label>
        <input
          type="number"
          value={endYear}
          min={1900}
          max={2200}
          style={styles.yearInput}
          onChange={(e) => onEndYearChange(Number(e.target.value))}
        />
        <button style={styles.btn} onClick={onStartStream} disabled={status === "streaming"}>
          {status === "streaming" ? "Streaming…" : "Run"}
        </button>
      </div>

      <div style={styles.row}>
        <button
          style={styles.btn}
          onClick={onPlayPause}
          disabled={years.length === 0}
        >
          {isPlaying ? "⏸ Pause" : "▶ Play"}
        </button>
        <span style={styles.yearDisplay}>
          {currentYear ?? "—"}
        </span>
        <span style={styles.label}>Speed:</span>
        {SPEEDS.map((s) => (
          <button
            key={s}
            style={{ ...styles.btn, ...(speed === s ? styles.btnActive : {}) }}
            onClick={() => onSpeedChange(s)}
          >
            {s}×
          </button>
        ))}
      </div>

      <div style={styles.row}>
        <input
          type="range"
          min={scrubMin}
          max={scrubMax}
          value={currentYear ?? scrubMin}
          style={{ flex: 1 }}
          disabled={years.length === 0}
          onChange={(e) => onScrub(Number(e.target.value))}
        />
      </div>

      <div style={styles.progressBar}>
        <div
          style={{
            ...styles.progressFill,
            width: `${total > 0 ? (buffered / total) * 100 : 0}%`,
          }}
        />
      </div>
      {status === "error" && (
        <div style={{ color: "#f66", fontSize: 12 }}>Stream error</div>
      )}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  panel: {
    background: "#16213e",
    padding: "10px 14px",
    display: "flex",
    flexDirection: "column",
    gap: 8,
    borderTop: "1px solid #333",
  },
  row: { display: "flex", alignItems: "center", gap: 8 },
  label: { fontSize: 12, color: "#aaa" },
  yearInput: {
    width: 70,
    background: "#0f3460",
    color: "#eee",
    border: "1px solid #444",
    borderRadius: 4,
    padding: "2px 6px",
    fontSize: 13,
  },
  btn: {
    background: "#0f3460",
    color: "#eee",
    border: "1px solid #444",
    borderRadius: 4,
    padding: "4px 10px",
    cursor: "pointer",
    fontSize: 13,
  },
  btnActive: { background: "#e94560", borderColor: "#e94560" },
  yearDisplay: { fontSize: 20, fontWeight: "bold", minWidth: 60, textAlign: "center" },
  progressBar: { height: 4, background: "#333", borderRadius: 2 },
  progressFill: { height: "100%", background: "#e94560", borderRadius: 2, transition: "width 0.3s" },
};
