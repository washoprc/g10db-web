import type { PanelCell, PanelGroup } from "../api/client";

export type ShotTableProps = {
  groupNames: string[];
  panels: PanelGroup[][];
  selectedShotNo: number | null;
  onSelect: (shotNo: number) => void;
};

/**
 * ショット一覧テーブル。
 * PHP ShowTable.php に相当するクラシックなグループ列表示。
 */
export default function ShotTable({
  groupNames,
  panels,
  selectedShotNo,
  onSelect,
}: ShotTableProps) {
  if (panels.length === 0) {
    return <p className="empty">ショットがありません。</p>;
  }

  return (
    <div className="tableWrap showTableWrap">
      <table className="showTable">
        <thead>
          <tr>
            {groupNames.map((name) => (
              <th key={name}>{name}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {panels.map((row, rowIndex) => {
            const shotNo = findShotNo(row);
            const selected = shotNo != null && shotNo === selectedShotNo;
            return (
              <tr
                key={`${shotNo ?? "x"}-${rowIndex}`}
                className={selected ? "selected" : undefined}
              >
                {groupNames.map((name, colIndex) => {
                  const group = row[colIndex];
                  const cells = group?.cells ?? [];
                  return (
                    <td key={name}>
                      <div className="panelStack">
                        {cells.map((cell, cellIndex) =>
                          renderCell(cell, cellIndex, onSelect),
                        )}
                      </div>
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** 行内のショット番号リンクを探す。 */
function findShotNo(row: PanelGroup[]): number | null {
  for (const group of row) {
    for (const cell of group.cells) {
      if (cell.isShotLink && cell.shotNo != null) {
        return cell.shotNo;
      }
    }
  }
  return null;
}

function renderCell(
  cell: PanelCell,
  cellIndex: number,
  onSelect: (shotNo: number) => void,
) {
  if (cell.isShotLink && cell.shotNo != null) {
    const shotNo = cell.shotNo;
    return (
      <a
        key={cellIndex}
        className="shotLink"
        href="#waveform-panel"
        title={`ショット ${shotNo} の波形を表示`}
        onClick={(event) => {
          event.preventDefault();
          onSelect(shotNo);
        }}
      >
        {cell.text}
      </a>
    );
  }
  return (
    <span key={cellIndex} className="panelLine">
      {cell.text}
    </span>
  );
}
