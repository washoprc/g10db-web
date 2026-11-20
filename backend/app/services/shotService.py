"""ショット検索サービス。

PHP の last.php / sn.php / day.php に相当する固定クエリのみを実行する。
日付検索は一致が無い場合に最寄り日付へフォールバックする。
arb.php のような任意 SQL は提供しない。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Literal

from app.config import getSettings
from app.db import fetchAll
from app.models.schemas import ShotListResponse, ShotRow
from app.services.viewPanel import buildPanelsForRows

SearchMode = Literal["latest", "byNumber", "byDate"]


def clampLimit(limit: int) -> int:
    """取得件数を 1〜MAX に丸める。"""
    settings = getSettings()
    return max(1, min(limit, settings.maxShotLimit))


def normalizeRow(raw: dict[str, Any]) -> ShotRow:
    """DB 行を ShotRow に正規化する。"""
    shotNo = raw.get("main__shotno")
    if shotNo is None:
        shotNo = raw.get("shotno")
    try:
        shotNoInt = int(shotNo) if shotNo is not None else None
    except (TypeError, ValueError):
        shotNoInt = None
    return ShotRow(shotNo=shotNoInt, columns=raw)


def buildDemoRecord(shotNo: int, shotDate: date, index: int) -> dict[str, Any]:
    """クラシック UI に近いデモ用 mainview 行。"""
    hour = 9 + (index % 8)
    minute = (index * 7) % 60
    timeStr = f"{hour:02d}:{minute:02d}:00"
    datetimeStr = f"{shotDate.isoformat()} {timeStr}"
    # 先頭ショットはレガシー画面に近い値、以降は差分が見えるよう変化させる
    cr = 2.50 - index * 0.05
    statusOn = 1 if index % 3 != 2 else 0
    statusPartial = 2 if index % 5 == 4 else statusOn
    raw: dict[str, Any] = {
        "main__shotno": shotNo,
        "main__indexno": index,
        "main__datetime": datetimeStr,
        "main__date": shotDate.isoformat(),
        "main__time": timeStr,
        "main__fixed": 1 if index == 0 else 0,
        "main__nlscan_pos": 0 if index == 0 else -999,
        "main__comment1": f"demo shot {shotNo}" if index == 0 else "",
        "main__comment2": "NBI+RF" if index == 0 else "",
        "main__gas": "H2",
        "main__comment": f"demo shot {shotNo}",
        # Coil
        "coil__auxiliary": "aux" if index == 0 else "",
        "coil__cr": cr,
        "coil__rb": 1.20 + index * 0.01,
        "coil__rt": 0.80,
        "coil__ab": 0.50,
        "coil__mr": 0.30,
        "coil__ft": 0.0,
        "coil__duty": 30 if index == 0 else 0,
        "coil__trans": "ok" if index == 0 else "",
        # PG
        "pg_e__time": "50-150" if index % 2 == 0 else "0-0",
        "pg_e__pressure": 100.0 if index % 2 == 0 else 0.0,
        "pg_e__pfn": 1.5 if index % 2 == 0 else 0.0,
        "pg_e__puff": 0.5 if index % 2 == 0 else 0.0,
        "pg_e__del": 10.0 if index % 2 == 0 else 0.0,
        "pg_e__status": statusOn if index % 2 == 0 else -1,
        "pg_w__time": "60-160" if index % 3 == 0 else "0-0",
        "pg_w__pressure": 90.0 if index % 3 == 0 else 0.0,
        "pg_w__pfn": 1.2 if index % 3 == 0 else 0.0,
        "pg_w__puff": 0.4 if index % 3 == 0 else 0.0,
        "pg_w__del": 8.0 if index % 3 == 0 else 0.0,
        "pg_w__status": statusOn if index % 3 == 0 else -1,
        # GP
        "gp1__time": "40-140",
        "gp1__pressure": 80.0,
        "gp1__a_w": 1 if index == 0 else 0,
        "gp1__a_w_text": "W" if index == 0 else "",
        "gp1__status": statusOn,
        "gp2__time": "45-145",
        "gp2__pressure": 75.0,
        "gp2__a_w": 0,
        "gp2__a_w_text": "",
        "gp2__status": statusOn,
        "gp1b__time": "0-0",
        "gp1b__pressure": 0.0,
        "gp1b__status": -1,
        "gp2b__time": "0-0",
        "gp2b__pressure": 0.0,
        "gp2b__status": -1,
        "gp3__time": "30-100" if index < 2 else "0-0",
        "gp3__pressure": 50.0 if index < 2 else 0.0,
        "gp3__status": statusOn if index < 2 else -1,
        "gp4__time": "0-0",
        "gp4__pressure": 0.0,
        "gp4__status": -1,
        "gp5__time": "0-0",
        "gp5__pressure": 0.0,
        "gp5__status": -1,
        "gp6__time": "0-0",
        "gp6__pressure": 0.0,
        "gp6__status": -1,
        "gp7__time": "0-0",
        "gp7__pressure": 0.0,
        "gp7__status": -1,
        "gp8__time": "0-0",
        "gp8__pressure": 0.0,
        "gp8__status": -1,
        # NBI
        "nbi_ae__time": "70-170" if index == 0 else "0-0",
        "nbi_ae__energy": 25.0 if index == 0 else 0.0,
        "nbi_ae__current": 40.0 if index == 0 else 0.0,
        "nbi_ae__status": statusOn if index == 0 else -1,
        "nbi_aw__time": "0-0",
        "nbi_aw__energy": 0.0,
        "nbi_aw__current": 0.0,
        "nbi_aw__status": -1,
        "nbi_se__time": "0-0",
        "nbi_se__energy": 0.0,
        "nbi_se__current": 0.0,
        "nbi_se__status": -1,
        "nbi_sw__time": "0-0",
        "nbi_sw__energy": 0.0,
        "nbi_sw__current": 0.0,
        "nbi_sw__status": -1,
        "nbi_c__time": "80-180" if index == 0 else "0-0",
        "nbi_c__energy": 30.0 if index == 0 else 0.0,
        "nbi_c__current": 50.0 if index == 0 else 0.0,
        "nbi_c__status": statusPartial if index == 0 else -1,
        # RF
        "rf1_pa1__ew": "E" if index == 0 else "",
        "rf1_pa1__freq": 6.36 if index == 0 else 0.0,
        "rf1_pa1__antenna": "A1" if index == 0 else "",
        "rf1_pa1__time": "90-190" if index == 0 else "0-0",
        "rf1_pa1__rise_time": 5.0 if index == 0 else 0.0,
        "rf1_pa1__power": 100.0 if index == 0 else 0.0,
        "rf1_pa1__status": statusOn if index == 0 else -1,
        "rf1_pa2__ew": "",
        "rf1_pa2__freq": 0.0,
        "rf1_pa2__time": "0-0",
        "rf1_pa2__power": 0.0,
        "rf1_pa2__status": -1,
        "rf2_pa3__ew": "",
        "rf2_pa3__freq": 0.0,
        "rf2_pa3__time": "0-0",
        "rf2_pa3__power": 0.0,
        "rf2_pa3__status": -1,
        "rf2_pa4__ew": "",
        "rf2_pa4__freq": 0.0,
        "rf2_pa4__time": "0-0",
        "rf2_pa4__power": 0.0,
        "rf2_pa4__status": -1,
        "rf3_pa5__ew": "",
        "rf3_pa5__freq": 0.0,
        "rf3_pa5__time": "0-0",
        "rf3_pa5__power": 0.0,
        "rf3_pa5__status": -1,
        # ECRH
        "ecrh_p1e__ps": "A " if index == 0 else "B ",
        "ecrh_p1e__time1": "100-200" if index == 0 else "0-0",
        "ecrh_p1e__time2": "0-0",
        "ecrh_p1e__power": 200.0 if index == 0 else 0.0,
        "ecrh_p1e__status": statusOn if index == 0 else -1,
        "ecrh_p1w__ps": "B ",
        "ecrh_p1w__time1": "0-0",
        "ecrh_p1w__time2": "0-0",
        "ecrh_p1w__power": 0.0,
        "ecrh_p1w__status": -1,
        "ecrh_be__ps": "B ",
        "ecrh_be__time1": "0-0",
        "ecrh_be__power": 0.0,
        "ecrh_be__status": -1,
        "ecrh_bw__ps": "B ",
        "ecrh_bw__time1": "0-0",
        "ecrh_bw__power": 0.0,
        "ecrh_bw__status": -1,
        "ecrh_c__ps": "B ",
        "ecrh_c__time1": "0-0",
        "ecrh_c__power": 0.0,
        "ecrh_c__status": -1,
        # G/F
        "ep__fg": 1 if index == 0 else 0,
        "ep__comment": "ep" if index == 0 else "",
        "cl__fg": 0,
        "br__fg": 0,
        "imt__fg": 0,
        # mlo
        "mlo1__fg": 1 if index == 0 else 0,
        "mlo1__length": 1.2 if index == 0 else 0.0,
        "mlo1__angle": 15.0 if index == 0 else 0.0,
        "mlo2__fg": 0,
        "mlo2__length": 0.0,
        "mlo2__angle": 0.0,
        "iris__fg": 0,
        "iris__diameter": 0.0,
        # dmod / gas
        "dmodule__status": statusOn if index == 0 else -1,
        "dmodule__angle_upp": 10.0 if index == 0 else 0.0,
        "dmodule__angle_low": 5.0 if index == 0 else 0.0,
        "pt_inlet__gas": "H2" if index == 0 else "",
        "pt_inlet__plenum": 1.0 if index == 0 else 0.0,
        "pt_inlet__delay": 5 if index == 0 else 0,
        "pt_inlet__width": 10 if index == 0 else 0,
        "pt_inlet__status": statusOn if index == 0 else -1,
        "pt_imp__gas": "",
        "pt_imp__plenum": 0.0,
        "pt_imp__status": -1,
        "pt_upper__gas": "",
        "pt_upper__plenum": 0.0,
        "pt_upper__status": -1,
    }
    return raw


def buildDemoShots(
    mode: SearchMode,
    *,
    limit: int,
    startShot: int | None = None,
    onDate: date | None = None,
) -> list[ShotRow]:
    """DB が無い環境向けのデモショット。"""
    today = date.today()
    # レガシー画面の先頭ショット番号に合わせる
    baseShot = startShot or 262065
    items: list[ShotRow] = []
    for index in range(limit):
        if mode == "latest":
            shotNo = baseShot - index
            shotDate = today - timedelta(days=index // 3)
        elif mode == "byNumber":
            shotNo = baseShot + index
            shotDate = today
        else:
            shotNo = baseShot + index
            shotDate = onDate or today
        raw = buildDemoRecord(shotNo, shotDate, index)
        items.append(normalizeRow(raw))
    return items


def makeResponse(
    mode: SearchMode,
    items: list[ShotRow],
    *,
    demoMode: bool,
    matchedDate: str | None = None,
    closestFallback: bool = False,
) -> ShotListResponse:
    """items から panels を付与した応答を作る。"""
    rows = [item.columns for item in items]
    groupNames, panels = buildPanelsForRows(rows)
    return ShotListResponse(
        mode=mode,
        count=len(items),
        items=items,
        groupNames=groupNames,
        panels=panels,
        demoMode=demoMode,
        matchedDate=matchedDate,
        closestFallback=closestFallback,
    )


def queryLatest(limit: int) -> ShotListResponse:
    """最新ショットを取得する（PHP last.php 相当）。"""
    limit = clampLimit(limit)
    settings = getSettings()
    if settings.useDemo:
        items = buildDemoShots("latest", limit=limit)
        return makeResponse("latest", items, demoMode=True)

    sql = """
        SELECT *
        FROM mainview
        ORDER BY main__shotno DESC
        LIMIT %s
    """
    rows = fetchAll(sql, (limit,))
    items = [normalizeRow(row) for row in rows]
    return makeResponse("latest", items, demoMode=False)


def queryByNumber(startShot: int, limit: int) -> ShotListResponse:
    """指定ショット番号以降を取得する（PHP sn.php 相当）。"""
    limit = clampLimit(limit)
    settings = getSettings()
    if settings.useDemo:
        items = buildDemoShots("byNumber", limit=limit, startShot=startShot)
        return makeResponse("byNumber", items, demoMode=True)

    sql = """
        SELECT *
        FROM mainview
        WHERE main__shotno >= %s
        ORDER BY main__shotno
        LIMIT %s
    """
    rows = fetchAll(sql, (startShot, limit))
    items = [normalizeRow(row) for row in rows]
    return makeResponse("byNumber", items, demoMode=False)


def queryByDate(onDate: date, limit: int) -> ShotListResponse:
    """指定日付のショットを取得する（PHP day.php 相当）。

    一致が無い場合は最寄り日付のショットへフォールバックする。
    """
    limit = clampLimit(limit)
    settings = getSettings()
    if settings.useDemo:
        items = buildDemoShots("byDate", limit=limit, onDate=onDate)
        return makeResponse(
            "byDate",
            items,
            demoMode=True,
            matchedDate=onDate.isoformat(),
            closestFallback=False,
        )

    exactSql = """
        SELECT *
        FROM mainview
        WHERE CAST(main__date AS date) = %s
        ORDER BY main__shotno
        LIMIT %s
    """
    rows = fetchAll(exactSql, (onDate, limit))
    if rows:
        items = [normalizeRow(row) for row in rows]
        return makeResponse(
            "byDate",
            items,
            demoMode=False,
            matchedDate=onDate.isoformat(),
            closestFallback=False,
        )

    # 最寄り日付: |date - target| 最小。同距離なら新しい日付を優先。
    closestSql = """
        SELECT CAST(main__date AS date) AS shot_date
        FROM mainview
        GROUP BY CAST(main__date AS date)
        ORDER BY ABS(CAST(main__date AS date) - %s), CAST(main__date AS date) DESC
        LIMIT 1
    """
    closestRows = fetchAll(closestSql, (onDate,))
    if not closestRows:
        return makeResponse(
            "byDate",
            [],
            demoMode=False,
            matchedDate=None,
            closestFallback=True,
        )

    closestDate = closestRows[0]["shot_date"]
    if isinstance(closestDate, datetime):
        closestDate = closestDate.date()
    elif isinstance(closestDate, str):
        closestDate = parseDateParam(closestDate)

    rows = fetchAll(exactSql, (closestDate, limit))
    items = [normalizeRow(row) for row in rows]
    return makeResponse(
        "byDate",
        items,
        demoMode=False,
        matchedDate=closestDate.isoformat() if isinstance(closestDate, date) else str(closestDate),
        closestFallback=True,
    )


def parseDateParam(value: str) -> date:
    """YYYY-MM-DD / YYYYMMDD / YYMMDD を date に変換する。"""
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%y%m%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError("日付は YYYY-MM-DD / YYYYMMDD / YYMMDD で指定してください")
