import { useEffect, useMemo, useState } from "react";
import createPlotlyComponent from "react-plotly.js/factory";
import Plotly from "plotly.js-basic-dist-min";
import {
  fetchWaveform,
  fetchWaveformDiagnose,
  fetchWaveformStatus,
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
  const [statusWarn, setStatusWarn] = useState<string | null>(null);
  const [diagnoseLine, setDiagnoseLine] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchWaveformStatus()
      .then((status) => {
        if (cancelled) return;
        const reasons: string[] = [];
        if (status.useDemo) {
          reasons.push("USE_DEMO=1");
        }
        if (!status.ftp?.passwordSet) {
          reasons.push("FTP_PASSWORD unset");
        }
        if (status.ftpProbe && !status.ftpProbe.ok) {
          reasons.push(
            `FTP probe failed${status.ftpProbe.error ? `: ${status.ftpProbe.error}` : ""}`,
          );
        }
        if (reasons.length > 0) {
          setStatusWarn(
            `Waveform runtime: ${reasons.join("; ")}. Check /api/waveforms/meta/status`,
          );
        } else {
          setStatusWarn(null);
        }
      })
      .catch(() => {
        if (!cancelled) setStatusWarn(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (shotNo == null) {
      setData(null);
      setDiagnoseLine(null);
      return;
    }
    let cancelled = false;
    setBusy(true);
    setError(null);
    setDiagnoseLine(null);
    fetchWaveform(shotNo, kind)
      .then(async (response) => {
        if (cancelled) return;
        setData(response);
        if (response.demoMode || response.series.length === 0) {
          try {
            const diag = await fetchWaveformDiagnose(shotNo, kind);
            if (cancelled) return;
            const okFetch = Object.values(diag.fetchResults || {}).filter(
              (r) => r && (r as { ok?: boolean }).ok,
            ).length;
            const okParse = Object.values(diag.parseResults || {}).filter(
              (r) => r && (r as { ok?: boolean }).ok,
            ).length;
            const shotDir =
              diag.shotDirExists === false
                ? "shotDir=missing"
                : diag.shotDirExists === true
                  ? "shotDir=ok"
                  : "shotDir=?";
            setDiagnoseLine(
              `diagnose: seriesCount=${diag.seriesCount}, ${shotDir}, ` +
                `fetchOk=${okFetch}, parseOk=${okParse}`,
            );
          } catch {
            if (!cancelled) setDiagnoseLine(null);
          }
        } else if (!cancelled) {
          setDiagnoseLine(null);
        }
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
      <section id="waveform-panel" className="waveformPanel" tabIndex={-1}>
        <h2>波形</h2>
        {statusWarn && (
          <p className="warnNote" role="status">
            {statusWarn}
          </p>
        )}
        <p className="empty">ショット番号のリンクをクリックすると波形を表示します。</p>
      </section>
    );
  }

  return (
    <section id="waveform-panel" className="waveformPanel" tabIndex={-1}>
      <div className="waveHeader">
        <h2>
          波形 — Shot {shotNo}
          {data != null ? (
            <span className="meta">
              {" "}
              {data.startMs}–{data.endMs} ms
            </span>
          ) : null}
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
      {statusWarn && (
        <p className="warnNote" role="status">
          {statusWarn}
        </p>
      )}
      {busy && <p>読み込み中…</p>}
      {error && <p className="error">{error}</p>}
      {data?.note && (
        <p className="warnNote" role="status">
          {data.note}
        </p>
      )}
      {diagnoseLine && (
        <p className="warnNote" role="status">
          {diagnoseLine}
        </p>
      )}
      {data && !busy && data.series.length > 0 && <WaveformChart data={data} />}
      {data && !busy && data.series.length === 0 && (
        <p className="empty">表示できる波形データがありません。</p>
      )}
    </section>
  );
}

type ChartProps = { data: WaveformResponse };

/** Plotly による複数系列チャート。 */
function WaveformChart({ data }: ChartProps) {
  const yUnit = data.series[0]?.unit || "";
  const yTitle = yUnit ? `${data.kind} [${yUnit}]` : data.kind;

  const plotData = useMemo(
    () =>
      data.series.map((series) => ({
        x: series.points.map((p) => p.t),
        y: series.points.map((p) => p.v),
        type: "scatter" as const,
        mode: "lines" as const,
        name: series.name,
      })),
    [data],
  );

  const layout = useMemo(
    () => ({
      autosize: true,
      margin: { t: 24, r: 16, b: 48, l: 72 },
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(248,250,248,0.9)",
      font: { family: "IBM Plex Sans, sans-serif", size: 12, color: "#1a2e1f" },
      xaxis: {
        title: { text: "Time [ms]" },
        gridcolor: "#d7e3d7",
        zeroline: false,
        range: [data.startMs, data.endMs],
      },
      yaxis: {
        title: { text: yTitle },
        gridcolor: "#d7e3d7",
        zeroline: false,
      },
      legend: { orientation: "h" as const, y: 1.12 },
      showlegend: true,
    }),
    [yTitle, data.startMs, data.endMs],
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
