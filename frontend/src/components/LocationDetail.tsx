import { LOCATION_KEYS, LocationVotingPrediction, SimulationLocationSnapshot } from "../types";

const DETAIL_ORDERS = {
  community: ["catholic", "protestant", "other", "none"],
  gender: ["female", "male", "other"],
  origin: ["ni", "roi", "gb", "other"],
  age: ["0-17", "18-35", "36-50", "51-70", "71+"],
} as const;

interface Props {
  locationId: string | null;
  year: number | null;
  detail: SimulationLocationSnapshot | null;
  voting: LocationVotingPrediction | null;
  pollingSource: string | null;
  onClose: () => void;
}

export function LocationDetail({ locationId, year, detail, voting, pollingSource, onClose }: Props) {
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
        {voting && <AreaVoting prediction={voting} source={pollingSource} />}
        <Section title="Community background" data={detail.religious_breakdown} order={DETAIL_ORDERS.community} />
        <Section title="Gender" data={detail.gender_breakdown} order={DETAIL_ORDERS.gender} />
        <Section title="Origin" data={detail.origin_breakdown} order={DETAIL_ORDERS.origin} />
        <Section title="Age bands" data={detail.age_bands} order={DETAIL_ORDERS.age} />
      </>}
    </aside>
  );
}

function AreaVoting({ prediction, source }: {
  prediction: LocationVotingPrediction;
  source: string | null;
}) {
  return <section className="area-voting" aria-labelledby="area-voting-title">
    <h3 id="area-voting-title">Estimated border-poll response</h3>
    <div className="area-voting-results">
      <span><b>{percent(prediction.unite_share)}</b> Unite</span>
      <span><b>{percent(prediction.remain_share)}</b> Remain</span>
      <span><b>{percent(prediction.undecided_share)}</b> Undecided</span>
    </div>
    <p>Estimated from this area's simulated adult age and community-background mix using {source ?? "the selected poll"} cross-tabs. Not area-level polling.</p>
  </section>;
}

function percent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

function Section({ title, data, order }: {
  title: string;
  data: Record<string, number>;
  order: readonly string[];
}) {
  const total = Object.values(data).reduce((sum, value) => sum + value, 0) || 1;
  const keys = [
    ...order.filter((key) => Object.prototype.hasOwnProperty.call(data, key)),
    ...Object.keys(data)
      .filter((key) => !(order as readonly string[]).includes(key))
      .sort(),
  ];
  return <section className="detail-section">
    <h3>{title}</h3>
    {keys.map((key) => {
      const value = data[key];
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
