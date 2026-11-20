import { FormEvent, useState } from "react";

export type SearchMode = "latest" | "byNumber" | "byDate";

export type ShotSearchProps = {
  busy: boolean;
  onSearch: (mode: SearchMode, value: string, limit: number) => void;
};

/**
 * ショット検索フォーム。
 * 最新 / 番号 / 日付の3モードに対応する。
 */
export default function ShotSearch({ busy, onSearch }: ShotSearchProps) {
  const [mode, setMode] = useState<SearchMode>("latest");
  const [value, setValue] = useState("");
  const [limit, setLimit] = useState(10);

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    onSearch(mode, value, limit);
  }

  return (
    <form className="searchPanel" onSubmit={handleSubmit}>
      <fieldset>
        <legend>ショット検索</legend>
        <div className="modeRow" role="radiogroup" aria-label="検索モード">
          {(
            [
              ["latest", "最新"],
              ["byNumber", "番号"],
              ["byDate", "日付"],
            ] as const
          ).map(([id, label]) => (
            <label key={id} className={mode === id ? "active" : ""}>
              <input
                type="radio"
                name="mode"
                value={id}
                checked={mode === id}
                onChange={() => setMode(id)}
              />
              {label}
            </label>
          ))}
        </div>

        {mode === "byNumber" && (
          <label className="field">
            開始ショット番号
            <input
              type="number"
              min={1}
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder="例: 120000"
              required
            />
          </label>
        )}

        {mode === "byDate" && (
          <label className="field">
            実験日
            <input
              type="date"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              required
            />
          </label>
        )}

        <label className="field">
          件数（最大30）
          <input
            type="number"
            min={1}
            max={30}
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
          />
        </label>

        <button type="submit" disabled={busy}>
          {busy ? "検索中…" : "検索"}
        </button>
      </fieldset>
    </form>
  );
}
