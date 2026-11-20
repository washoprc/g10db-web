"""PHP DataConverter.php（ViewPanelConverter）のポート。

ShowTable 用に mainview 行をグループ列パネルへ変換する。
"""

from __future__ import annotations

from typing import Any

from app.models.schemas import PanelCell, PanelGroup
from app.services.configLoader import loadG10dbGroups, loadG10dbTableMap

STATUS_OFF = "-"
STATUS_ON = "○"
STATUS_PARTIAL = "×"
EMPTY_MARKER = "-"


class ViewPanelConverter:
    """GroupList / TableList に基づき 1 行分の表示パネルを組み立てる。"""

    def __init__(
        self,
        groups: list[Any] | None = None,
        tableMap: dict[str, Any] | None = None,
    ) -> None:
        self.groups = groups if groups is not None else loadG10dbGroups()
        self.tableMap = tableMap if tableMap is not None else loadG10dbTableMap()

    def groupNames(self) -> list[str]:
        """表示するグループ名一覧。"""
        names: list[str] = []
        for group in self.groups:
            if isinstance(group, dict):
                name = group.get("groupName")
                if isinstance(name, str):
                    names.append(name)
        return names

    def getViewPanelArray(
        self,
        record: dict[str, Any],
        prevRecord: dict[str, Any] | None = None,
    ) -> list[PanelGroup]:
        """1 レコード分のグループパネル配列を返す。"""
        panels: list[PanelGroup] = []
        for group in self.groups:
            if not isinstance(group, dict):
                continue
            panels.append(self.createRecordPanel(group, record, prevRecord))
        return panels

    def createRecordPanel(
        self,
        group: dict[str, Any],
        record: dict[str, Any],
        prevRecord: dict[str, Any] | None,
    ) -> PanelGroup:
        """1 グループ分のセル列を組み立てる。"""
        groupName = str(group.get("groupName") or "")
        isCommentGroup = groupName == "Comment"
        cells: list[PanelCell] = []

        tables = group.get("tables") or []
        if not isinstance(tables, list):
            tables = []

        for tableRef in tables:
            if not isinstance(tableRef, dict):
                continue
            tableName = str(tableRef.get("name") or "")
            showFlag = int(tableRef.get("show") or 0)
            tableDef = self.tableMap.get(tableName)
            if not tableDef:
                continue
            fields = tableDef.get("fields") or []
            if not isinstance(fields, list):
                continue

            tableCells: list[PanelCell] = []
            for field in fields:
                if not isinstance(field, dict):
                    continue
                commentFlag = str(field.get("comment") or "0")
                if isCommentGroup:
                    if commentFlag != "1":
                        continue
                elif commentFlag == "1":
                    continue

                cell = self.getFormatedString(tableName, field, record, prevRecord)
                if cell is not None:
                    tableCells.append(cell)

            if showFlag and tableCells:
                cells.append(PanelCell(text=tableName, isShotLink=False))
            cells.extend(tableCells)

        if not cells:
            cells.append(PanelCell(text=EMPTY_MARKER, isShotLink=False))
        return PanelGroup(cells=cells)

    def getFormatedString(
        self,
        tableName: str,
        field: dict[str, Any],
        record: dict[str, Any],
        prevRecord: dict[str, Any] | None,
    ) -> PanelCell | None:
        """フィールド 1 つを表示用セルに整形する。非表示なら None。"""
        fieldName = str(field.get("fieldName") or "")
        fullKey = f"{tableName}__{fieldName}"
        value = record.get(fullKey)
        if value is None and fieldName == "datetime":
            # date + time を結合（デモ／一部ビュー向け）
            datePart = record.get("main__date")
            timePart = record.get("main__time")
            if datePart is not None or timePart is not None:
                value = f"{datePart or ''} {timePart or ''}".strip()

        if self._isHideValue(value, field.get("hideValue")):
            return None

        if prevRecord is not None:
            prevValue = prevRecord.get(fullKey)
            if prevValue is None and fieldName == "datetime":
                datePart = prevRecord.get("main__date")
                timePart = prevRecord.get("main__time")
                if datePart is not None or timePart is not None:
                    prevValue = f"{datePart or ''} {timePart or ''}".strip()
            if self._valuesEqual(value, prevValue):
                return None

        otherInf = str(field.get("otherInf") or "")
        if fieldName == "shotno":
            try:
                shotNo = int(value)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                shotNo = None
            return PanelCell(text=str(value), isShotLink=True, shotNo=shotNo)

        if otherInf == "status":
            text = self._formatStatus(value)
            return PanelCell(text=text, isShotLink=False) if text else None

        if otherInf == "ONOFF":
            text = self._formatOnoff(value)
            return PanelCell(text=text, isShotLink=False) if text else None

        if otherInf == "fg":
            text = self._formatFg(value)
            return PanelCell(text=text, isShotLink=False) if text else None

        body = self._formatByType(value, field)
        if body == "":
            return None
        header = str(field.get("header") or "")
        footer = str(field.get("footer") or "")
        return PanelCell(text=f"{header}{body}{footer}", isShotLink=False)

    def _formatStatus(self, value: Any) -> str:
        try:
            code = int(float(value))
        except (TypeError, ValueError):
            return str(value)
        if code == 0:
            return STATUS_OFF
        if code == 1:
            return STATUS_ON
        if code == 2:
            return STATUS_PARTIAL
        return str(value)

    def _formatOnoff(self, value: Any) -> str:
        try:
            code = int(float(value))
        except (TypeError, ValueError):
            return str(value)
        if code == 0:
            return STATUS_OFF
        if code == 1:
            return STATUS_ON
        return str(value)

    def _formatFg(self, value: Any) -> str:
        try:
            code = int(float(value))
        except (TypeError, ValueError):
            return str(value) if value not in (None, "") else ""
        if code == 0:
            return ""
        return STATUS_ON

    def _formatByType(self, value: Any, field: dict[str, Any]) -> str:
        if value is None:
            return ""
        fmt = str(field.get("format") or "")
        fieldType = str(field.get("fieldType") or "")
        if fieldType in {"Float", "Integer", "Short"} or fmt != "":
            try:
                number = float(value)
            except (TypeError, ValueError):
                return str(value)
            if fmt.isdigit():
                return f"{number:.{int(fmt)}f}"
            if fieldType == "Integer" or fieldType == "Short":
                return str(int(number))
            return str(value)
        return str(value)

    def _isHideValue(self, value: Any, hideValue: Any) -> bool:
        if value is None:
            return True
        if hideValue is None:
            return False
        hideStr = str(hideValue)
        valueStr = str(value)
        if valueStr == hideStr:
            return True
        try:
            return float(value) == float(hideValue)
        except (TypeError, ValueError):
            return False

    def _valuesEqual(self, left: Any, right: Any) -> bool:
        if left is None and right is None:
            return True
        if left is None or right is None:
            return False
        if str(left) == str(right):
            return True
        try:
            return float(left) == float(right)
        except (TypeError, ValueError):
            return False


def buildPanelsForRows(
    rows: list[dict[str, Any]],
) -> tuple[list[str], list[list[PanelGroup]]]:
    """複数行から (groupNames, panels) を生成する。"""
    converter = ViewPanelConverter()
    groupNames = converter.groupNames()
    panels: list[list[PanelGroup]] = []
    prev: dict[str, Any] | None = None
    for row in rows:
        panels.append(converter.getViewPanelArray(row, prev))
        prev = row
    return groupNames, panels
