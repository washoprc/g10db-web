"""PostgreSQL 接続ヘルパー。

任意 SQL は受け付けず、呼び出し側が固定クエリのみを実行する。
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg.rows import dict_row

from app.config import getSettings


@contextmanager
def openConnection() -> Iterator[psycopg.Connection]:
    """読み取り専用に近い用途の接続を開く。"""
    settings = getSettings()
    with psycopg.connect(settings.dsn, row_factory=dict_row) as conn:
        yield conn


def fetchAll(sql: str, params: Sequence[Any] | None = None) -> list[dict[str, Any]]:
    """固定 SQL を実行し、辞書行のリストを返す。

    Args:
        sql: プレースホルダ付きの固定クエリ。呼び出し側で組み立てること。
        params: バインドパラメータ。
    """
    with openConnection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            rows = cur.fetchall()
            return [dict(row) for row in rows]
