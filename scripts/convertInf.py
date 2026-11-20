#!/usr/bin/env python3
"""GroupList.inf / TableList.inf を JSON に変換する補助スクリプト。

旧 PHP 設定の簡易パーサ。行形式の揺れに耐えるため、
`key=value` と空白区切りの両方を受け付ける。

使い方:
  python3 scripts/convertInf.py path/to/GroupList.inf path/to/TableList.inf -o config/
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path
from typing import Any


def parseLooseInf(path: Path) -> dict[str, Any]:
    """inf 風テキストをゆるくパースする。"""
    groups: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    section = "groups"

    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        lower = line.lower()
        if "table" in lower and ("list" in lower or lower.startswith("[")):
            section = "tables"
            current = None
            continue
        if "group" in lower and ("list" in lower or lower.startswith("[")):
            section = "groups"
            current = None
            continue

        if "=" in line:
            key, value = [p.strip() for p in line.split("=", 1)]
            if key.lower() in {"id", "name", "group", "table"}:
                current = {"id": value}
                if section == "groups":
                    groups.append(current)
                else:
                    tables.append(current)
            elif current is not None:
                if key.lower() == "channels":
                    current["channels"] = [c.strip() for c in re.split(r"[,\\s]+", value) if c.strip()]
                else:
                    current[key] = value
            continue

        parts = re.split(r"[,\\s]+", line)
        if len(parts) >= 2:
            entry = {"id": parts[0], "channels": parts[1:]} if section == "tables" else {
                "id": parts[0],
                "label": parts[1],
                "unit": parts[2] if len(parts) > 2 else "",
            }
            if section == "groups":
                groups.append(entry)
            else:
                tables.append(entry)

    if groups:
        return {"source": path.name, "convertedAt": date.today().isoformat(), "groups": groups}
    return {"source": path.name, "convertedAt": date.today().isoformat(), "tables": tables}


def main() -> None:
    """CLI エントリ。"""
    parser = argparse.ArgumentParser(description="Convert GroupList/TableList .inf to JSON")
    parser.add_argument("inputs", nargs="+", type=Path, help=".inf ファイル")
    parser.add_argument("-o", "--output", type=Path, default=Path("config"))
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    for path in args.inputs:
        data = parseLooseInf(path)
        if "groups" in data:
            out = args.output / "GroupList.json"
        else:
            out = args.output / "TableList.json"
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {out}")


if __name__ == "__main__":
    main()
