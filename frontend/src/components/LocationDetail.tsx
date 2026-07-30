import { useEffect, useState } from "react";

import { LocationDetail as LocationDetailType } from "../types";

interface Props {
  locationId: string | null;
  onClose: () => void;
}

export function LocationDetail({ locationId, onClose }: Props) {
  const [detail, setDetail] = useState<LocationDetailType | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!locationId) { setDetail(null); return; }
    setLoading(true);
    fetch(`/api/population/location/${locationId}`)
      .then((r) => r.json())
      .then((d) => { setDetail(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [locationId]);

  if (!locationId) return null;

  return (
    <div style={styles.panel}>
      <button style={styles.close} onClick={onClose}>✕</button>
      {loading && <div style={styles.loading}>Loading…</div>}
      {detail && (
        <>
          <h3 style={styles.title}>{detail.location.replace(/_/g, " ").toUpperCase()}</h3>
          <div style={styles.stat}>Population: <strong>{detail.total.toLocaleString()}</strong></div>

          <Section title="Religion" data={detail.religious_breakdown} />
          <Section title="Gender" data={detail.gender_breakdown} />
          <Section title="Origin" data={detail.origin_breakdown} />
          <Section title="Age Bands" data={detail.age_bands} />
        </>
      )}
    </div>
  );
}

function Section({ title, data }: { title: string; data: Record<string, number> }) {
  const total = Object.values(data).reduce((a, b) => a + b, 0) || 1;
  return (
    <div style={{ marginTop: 10 }}>
      <div style={styles.sectionTitle}>{title}</div>
      {Object.entries(data).map(([k, v]) => (
        <div key={k} style={styles.barRow}>
          <span style={styles.barLabel}>{k}</span>
          <div style={styles.barTrack}>
            <div style={{ ...styles.barFill, width: `${(v / total) * 100}%` }} />
          </div>
          <span style={styles.barValue}>{v.toLocaleString()}</span>
        </div>
      ))}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  panel: {
    position: "absolute",
    top: 10,
    right: 10,
    width: 280,
    background: "#16213e",
    border: "1px solid #333",
    borderRadius: 8,
    padding: 16,
    zIndex: 1000,
    maxHeight: "80vh",
    overflowY: "auto",
  },
  close: {
    position: "absolute",
    top: 8,
    right: 10,
    background: "none",
    border: "none",
    color: "#aaa",
    cursor: "pointer",
    fontSize: 16,
  },
  title: { fontSize: 14, fontWeight: "bold", marginBottom: 8, paddingRight: 20 },
  stat: { fontSize: 13, color: "#ccc" },
  loading: { color: "#aaa", fontSize: 13 },
  sectionTitle: { fontSize: 11, color: "#888", textTransform: "uppercase", marginBottom: 4 },
  barRow: { display: "flex", alignItems: "center", gap: 6, marginBottom: 3 },
  barLabel: { fontSize: 11, color: "#ccc", width: 70, flexShrink: 0 },
  barTrack: { flex: 1, height: 8, background: "#0f3460", borderRadius: 4 },
  barFill: { height: "100%", background: "#e94560", borderRadius: 4 },
  barValue: { fontSize: 11, color: "#aaa", width: 45, textAlign: "right" },
};
