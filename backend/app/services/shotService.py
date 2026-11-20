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


def buildDemoShots(
    mode: SearchMode,
    *,
    limit: int,
    startShot: int | None = None,
    onDate: date | None = None,
) -> list[ShotRow]:
    """DB が無い環境向けのデモショット。"""
    today = date.today()
    baseShot = startShot or 120000
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
        raw = {
            "main__shotno": shotNo,
            "main__date": shotDate.isoformat(),
            "main__time": f"{9 + (index % 8):02d}:{(index * 7) % 60:02d}:00",
            "main__gas": "H2",
            "main__comment": f"demo shot {shotNo}",
        }
        items.append(normalizeRow(raw))
    return items


def queryLatest(limit: int) -> ShotListResponse:
    """最新ショットを取得する（PHP last.php 相当）。"""
    limit = clampLimit(limit)
    settings = getSettings()
    if settings.useDemo:
        items = buildDemoShots("latest", limit=limit)
        return ShotListResponse(mode="latest", count=len(items), items=items, demoMode=True)

    sql = """
        SELECT *
        FROM mainview
        ORDER BY main__shotno DESC
        LIMIT %s
    """
    rows = fetchAll(sql, (limit,))
    items = [normalizeRow(row) for row in rows]
    return ShotListResponse(mode="latest", count=len(items), items=items, demoMode=False)


def queryByNumber(startShot: int, limit: int) -> ShotListResponse:
    """指定ショット番号以降を取得する（PHP sn.php 相当）。"""
    limit = clampLimit(limit)
    settings = getSettings()
    if settings.useDemo:
        items = buildDemoShots("byNumber", limit=limit, startShot=startShot)
        return ShotListResponse(mode="byNumber", count=len(items), items=items, demoMode=True)

    sql = """
        SELECT *
        FROM mainview
        WHERE main__shotno >= %s
        ORDER BY main__shotno
        LIMIT %s
    """
    rows = fetchAll(sql, (startShot, limit))
    items = [normalizeRow(row) for row in rows]
    return ShotListResponse(mode="byNumber", count=len(items), items=items, demoMode=False)


def queryByDate(onDate: date, limit: int) -> ShotListResponse:
    """指定日付のショットを取得する（PHP day.php 相当）。

    一致が無い場合は最寄り日付のショットへフォールバックする。
    """
    limit = clampLimit(limit)
    settings = getSettings()
    if settings.useDemo:
        items = buildDemoShots("byDate", limit=limit, onDate=onDate)
        return ShotListResponse(
            mode="byDate",
            count=len(items),
            items=items,
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
        return ShotListResponse(
            mode="byDate",
            count=len(items),
            items=items,
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
        return ShotListResponse(
            mode="byDate",
            count=0,
            items=[],
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
    return ShotListResponse(
        mode="byDate",
        count=len(items),
        items=items,
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
