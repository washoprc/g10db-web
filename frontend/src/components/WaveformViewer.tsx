import { useEffect, useMemo, useState } from "react";
import createPlotlyComponent from "react-plotly.js/factory";
import Plotly from "plotly.js-basic-dist-min";
import {
  fetchWaveform,
  type WaveformKind,
  type WaveformResponse,
} from "../api/client";

const Plot = createPlotlyComponent(Plotly);

export type WaveformViewerProps = {
  shotNo: number | null;
};

const KINDS: WaveformKind[] = ["Ha", "DM", "NL", "VCC"];

/**
 * Ha / DM / NL / VCC 波形ビューア（Plotly）。
 * 旧 TekeTekeKun + jpgraph 相当。
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

/** Plotly による複数系列チャート。 */
function WaveformChart({ data }: ChartProps) {
  const plotData = useMemo(
    () =>
      data.series.map((series) => ({
        x: series.points.map((p) => p.t),
        y: series.points.map((p) => p.v),
        type: "scatter" as const,
        mode: "lines" as const,
        name: series.unit ? `${series.name} (${series.unit})` : series.name,
      })),
    [data],
  );

  const layout = useMemo(
    () => ({
      autosize: true,
      margin: { t: 24, r: 16, b: 48, l: 56 },
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(248,250,248,0.9)",
      font: { family: "IBM Plex Sans, sans-serif", size: 12, color: "#1a2e1f" },
      xaxis: { title: "t [ms]", gridcolor: "#d7e3d7", zeroline: false },
      yaxis: { title: data.kind, gridcolor: "#d7e3d7", zeroline: false },
      legend: { orientation: "h" as const, y: 1.12 },
      showlegend: true,
    }),
    [data.kind],
  );

  return (
    <div className="chartBlock">
      <Plot
        data={plotData}
        layout={layout}
        config={{ displayModeBar: false, responsive: true }}
        style={{ width: "100%", height: "320px" }}
        useResizeHandler
      />
    </div>
  );
}
