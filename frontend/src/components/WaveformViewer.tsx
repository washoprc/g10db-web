import { useEffect, useMemo, useState } from "react";
import {
  fetchWaveform,
  type WaveformKind,
  type WaveformResponse,
} from "../api/client";

export type WaveformViewerProps = {
  shotNo: number | null;
};

const KINDS: WaveformKind[] = ["Ha", "DM", "NL", "VCC"];

/**
 * Ha / DM / NL / VCC 波形ビューア。
 * SVG 折れ線で描画する（旧 jpgraph 相当の簡易版）。
 */
export default function WaveformViewer({ shotNo }: WaveformViewerProps) {
  const [kind, setKind] = useState<WaveformKind>("Ha");
  const [data, setData] = useState<WaveformResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (shotNo == null) {
      setData(null);
      return;
    }
    let cancelled = false;
    setBusy(true);
    setError(null);
    fetchWaveform(shotNo, kind)
      .then((response) => {
        if (!cancelled) setData(response);
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setBusy(false);
      });
    return () => {
      cancelled = true;
    };
  }, [shotNo, kind]);

  if (shotNo == null) {
    return (
      <section className="waveformPanel">
        <h2>波形</h2>
        <p className="empty">テーブルの行を選ぶと波形を表示します。</p>
      </section>
    );
  }

  return (
    <section className="waveformPanel">
      <div className="waveHeader">
        <h2>
          波形 — Shot {shotNo}
          {data?.demoMode ? <span className="badge">demo</span> : null}
        </h2>
        <div className="kindTabs" role="tablist">
          {KINDS.map((item) => (
            <button
              key={item}
              type="button"
              role="tab"
              aria-selected={kind === item}
              className={kind === item ? "active" : ""}
              onClick={() => setKind(item)}
            >
              {item}
            </button>
          ))}
        </div>
      </div>
      {busy && <p>読み込み中…</p>}
      {error && <p className="error">{error}</p>}
      {data && !busy && <WaveformChart data={data} />}
      {data?.note && <p className="note">{data.note}</p>}
    </section>
  );
}

type ChartProps = { data: WaveformResponse };

/** SVG による複数系列チャート。 */
function WaveformChart({ data }: ChartProps) {
  const width = 720;
  const height = 280;
  const pad = { top: 16, right: 16, bottom: 28, left: 48 };

  const geometry = useMemo(() => {
    const allPoints = data.series.flatMap((s) => s.points);
    const tMin = Math.min(...allPoints.map((p) => p.t));
    const tMax = Math.max(...allPoints.map((p) => p.t));
    const vMin = Math.min(...allPoints.map((p) => p.v));
    const vMax = Math.max(...allPoints.map((p) => p.v));
    const spanT = tMax - tMin || 1;
    const spanV = vMax - vMin || 1;
    const innerW = width - pad.left - pad.right;
    const innerH = height - pad.top - pad.bottom;
    const x = (t: number) => pad.left + ((t - tMin) / spanT) * innerW;
    const y = (v: number) => pad.top + (1 - (v - vMin) / spanV) * innerH;
    return { x, y, tMin, tMax, vMin, vMax };
  }, [data, height, pad.bottom, pad.left, pad.right, pad.top, width]);

  const colors = ["#0b6e4f", "#1b4965", "#c1121f", "#7b2cbf"];

  return (
    <div className="chartBlock">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${data.kind} waveform`}>
        <rect x={0} y={0} width={width} height={height} className="chartBg" />
        {data.series.map((series, index) => {
          const d = series.points
            .map((p, i) => `${i === 0 ? "M" : "L"}${geometry.x(p.t)},${geometry.y(p.v)}`)
            .join(" ");
          return (
            <path
              key={series.name}
              d={d}
              fill="none"
              stroke={colors[index % colors.length]}
              strokeWidth={1.8}
            />
          );
        })}
        <text x={pad.left} y={height - 8} className="axisLabel">
          t [ms] {geometry.tMin.toFixed(0)} – {geometry.tMax.toFixed(0)}
        </text>
      </svg>
      <ul className="legend">
        {data.series.map((series, index) => (
          <li key={series.name} style={{ color: colors[index % colors.length] }}>
            {series.name}
            {series.unit ? ` (${series.unit})` : ""}
          </li>
        ))}
      </ul>
    </div>
  );
}
