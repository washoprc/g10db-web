import type { ShotRow } from "../api/client";

export type ShotTableProps = {
  items: ShotRow[];
  selectedShotNo: number | null;
  onSelect: (shotNo: number) => void;
};

/**
 * ショット一覧テーブル。
 * PHP ShowTable.php に相当する。
 */
export default function ShotTable({
  items,
  selectedShotNo,
  onSelect,
}: ShotTableProps) {
  if (items.length === 0) {
    return <p className="empty">ショットがありません。</p>;
  }

  const columnKeys = collectColumns(items);

  return (
    <div className="tableWrap">
      <table>
        <thead>
          <tr>
            {columnKeys.map((key) => (
              <th key={key}>{prettyColumn(key)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {items.map((item, index) => {
            const shotNo = item.shotNo;
            const selected = shotNo != null && shotNo === selectedShotNo;
            return (
              <tr
                key={`${shotNo ?? "x"}-${index}`}
                className={selected ? "selected" : undefined}
                onClick={() => {
                  if (shotNo != null) onSelect(shotNo);
                }}
              >
                {columnKeys.map((key) => (
                  <td key={key}>{formatCell(item.columns[key])}</td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** 表示列を収集する（ショット番号を先頭に）。 */
function collectColumns(items: ShotRow[]): string[] {
  const keys = new Set<string>();
  for (const item of items) {
    Object.keys(item.columns).forEach((key) => keys.add(key));
  }
  const ordered = Array.from(keys);
  ordered.sort((a, b) => {
    if (a === "main__shotno") return -1;
    if (b === "main__shotno") return 1;
    return a.localeCompare(b);
  });
  return ordered.slice(0, 8);
}

/** main__shotno → Shot No のような表示名。 */
function prettyColumn(key: string): string {
  return key.replace(/^main__/, "").replaceAll("_", " ");
}

function formatCell(value: unknown): string {
  if (value == null) return "";
  return String(value);
}
