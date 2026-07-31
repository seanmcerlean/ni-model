import { LOCATION_KEYS, SimulationLocationSnapshot } from "../types";

interface Props {
  locationId: string | null;
  year: number | null;
  detail: SimulationLocationSnapshot | null;
  onClose: () => void;
}

export function LocationDetail({ locationId, year, detail, onClose }: Props) {
  if (!locationId) return null;
  return (
    <aside className="location-panel" aria-labelledby="location-title">
      <button className="location-close" onClick={onClose} aria-label="Close area details">✕</button>
      <div className="location-eyebrow">AREA SNAPSHOT {year ?? "—"}</div>
      <h2 id="location-title">{LOCATION_KEYS[locationId] ?? locationId}</h2>
      {!detail && <div className="location-empty">Run the model to see area statistics.</div>}
      {detail && <>
        <div className="location-population">{detail.total.toLocaleString()}</div>
        <div className="location-population-label">simulated residents</div>
        <Section title="Community background" data={detail.religious_breakdown} />
        <Section title="Gender" data={detail.gender_breakdown} />
        <Section title="Origin" data={detail.origin_breakdown} />
        <Section title="Age bands" data={detail.age_bands} />
      </>}
    </aside>
  );
}

function Section({ title, data }: { title: string; data: Record<string, number> }) {
  const total = Object.values(data).reduce((sum, value) => sum + value, 0) || 1;
  return <section className="detail-section">
    <h3>{title}</h3>
    {Object.entries(data).map(([key, value]) => {
      const share = (value / total) * 100;
      return <div key={key} className="detail-bar-row">
        <span className="detail-bar-label">{friendly(key)}</span>
        <div className="detail-bar-track" role="img" aria-label={`${friendly(key)} ${share.toFixed(1)}%`}>
          <div className={`detail-bar-fill category-${key}`} style={{ width: `${share}%` }} />
        </div>
        <span className="detail-bar-value"><b>{share.toFixed(1)}%</b>{value.toLocaleString()}</span>
      </div>;
    })}
  </section>;
}

function friendly(value: string) {
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}
