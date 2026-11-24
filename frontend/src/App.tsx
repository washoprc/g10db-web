import { useCallback, useState } from "react";
import {
  fetchLatestShots,
  fetchShotsByDate,
  fetchShotsByNumber,
  type ShotListResponse,
} from "./api/client";
import ShotSearch, { type SearchMode } from "./components/ShotSearch";
import ShotTable from "./components/ShotTable";
import WaveformViewer from "./components/WaveformViewer";

const WAVEFORM_PANEL_ID = "waveform-panel";

/**
 * 波形パネルへスクロールし、フォーカスを移す。
 */
function scrollToWaveformPanel() {
  const panel = document.getElementById(WAVEFORM_PANEL_ID);
  if (!panel) return;
  panel.scrollIntoView({ behavior: "smooth", block: "start" });
  if (typeof panel.focus === "function") {
    panel.focus({ preventScroll: true });
  }
}

/**
 * g10db-web メイン画面。
 * ショット検索と波形表示を一つの画面にまとめる。
 */
export default function App() {
  const [result, setResult] = useState<ShotListResponse | null>(null);
  const [selectedShotNo, setSelectedShotNo] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSearch = useCallback(
    async (mode: SearchMode, value: string, limit: number) => {
      setBusy(true);
      setError(null);
      try {
        let response: ShotListResponse;
        if (mode === "latest") {
          response = await fetchLatestShots(limit);
        } else if (mode === "byNumber") {
          response = await fetchShotsByNumber(Number(value), limit);
        } else {
          response = await fetchShotsByDate(value, limit);
        }
        setResult(response);
        const first = response.items.find((item) => item.shotNo != null)?.shotNo ?? null;
        setSelectedShotNo(first);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setBusy(false);
      }
    },
    [],
  );

  /** ショット番号リンク: 選択して波形パネルへ遷移する。 */
  const handleSelectShot = useCallback((shotNo: number) => {
    setSelectedShotNo(shotNo);
    // 描画後にスクロール（同一ショット再クリックでも遷移）
    window.requestAnimationFrame(() => {
      scrollToWaveformPanel();
    });
  }, []);

  return (
    <div className="appShell">
      <header className="hero">
        <h1 className="brand">g10db-web</h1>
      </header>

      <main className="layout">
        <ShotSearch busy={busy} onSearch={handleSearch} />

        <section className="results">
          <div className="resultsHeader">
            <h2>検索結果</h2>
            {result?.demoMode ? <span className="badge">demo mode</span> : null}
            {result?.closestFallback ? (
              <span className="badge">closest date → {result.matchedDate}</span>
            ) : null}
            {result ? <span className="meta">{result.count} 件 / {result.mode}</span> : null}
          </div>
          {error && <p className="error">{error}</p>}
          {result ? (
            <ShotTable
              groupNames={result.groupNames}
              panels={result.panels}
              selectedShotNo={selectedShotNo}
              onSelect={handleSelectShot}
            />
          ) : (
            <p className="empty">検索を実行してください。</p>
          )}
        </section>

        <WaveformViewer shotNo={selectedShotNo} />
      </main>

      <footer>
        <p>Plasma Research Center / University of Tsukuba — FastAPI + React rebuild of g10db</p>
      </footer>
    </div>
  );
}
