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

  return (
    <div className="appShell">
      <header className="hero">
        <p className="brand">g10db-web</p>
        <h1>GAMMA 10 / PDX ショット・波形ビューア</h1>
        <p className="lede">
          旧 PHP g10db（G10DB + TekeTekeKun）を FastAPI + React に移行した閲覧画面です。
          任意 SQL は廃止し、最新・番号・日付検索と Ha / DM / NL / VCC 波形に限定しています。
        </p>
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
              items={result.items}
              selectedShotNo={selectedShotNo}
              onSelect={setSelectedShotNo}
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
