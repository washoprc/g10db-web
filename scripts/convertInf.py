#!/usr/bin/env python3
"""GroupList.inf / TableList.inf（CP932）を UTF-8 JSON に変換する。

旧 PHP 設定のパーサ。行形式の揺れに耐えるため、
`key=value`・空白区切り・タブ区切りを受け付ける。

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


def readInfText(path: Path) -> str:
    """CP932 → UTF-8 を優先し、失敗時は utf-8 / latin-1 にフォールバック。"""
    raw = path.read_bytes()
    for encoding in ("cp932", "shift_jis", "utf-8", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def parseLooseInf(path: Path) -> dict[str, Any]:
    """inf 風テキストをゆるくパースする。"""
    groups: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    section = "groups"
    preferTables = "table" in path.name.lower()

    if preferTables:
        section = "tables"

    for raw in readInfText(path).splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        lower = line.lower()
        if lower.startswith("[") and lower.endswith("]"):
            label = lower.strip("[]")
            if "table" in label:
                section = "tables"
            elif "group" in label or "detector" in label:
                section = "groups"
            current = None
            continue
        if "table" in lower and ("list" in lower or ":" in lower):
            section = "tables"
            current = None
            continue
        if "group" in lower and ("list" in lower or ":" in lower):
            section = "groups"
            current = None
            continue

        if "=" in line:
            key, value = [p.strip() for p in line.split("=", 1)]
            keyLower = key.lower()
            if keyLower in {"id", "name", "group", "table", "detector"}:
                current = {"id": value}
                if section == "groups":
                    groups.append(current)
                else:
                    tables.append(current)
            elif current is not None:
                if keyLower in {"channels", "ch", "cols", "columns"}:
                    current["channels"] = [
                        c.strip() for c in re.split(r"[,;\s]+", value) if c.strip()
                    ]
                elif keyLower in {"label", "title", "disp", "display"}:
                    current["label"] = value
                elif keyLower in {"unit", "units"}:
                    current["unit"] = value
                elif keyLower in {"desc", "description", "comment"}:
                    current["description"] = value
                else:
                    current[key] = value
            continue

        parts = re.split(r"[\t,;]+|\s{2,}", line)
        parts = [p.strip() for p in parts if p.strip()]
        if len(parts) == 1:
            parts = re.split(r"\s+", line)
        if len(parts) >= 2:
            if section == "tables":
                entry: dict[str, Any] = {"id": parts[0], "channels": parts[1:]}
                tables.append(entry)
            else:
                entry = {
                    "id": parts[0],
                    "label": parts[1],
                    "unit": parts[2] if len(parts) > 2 else "",
                    "description": parts[3] if len(parts) > 3 else "",
                }
                groups.append(entry)

    payload: dict[str, Any] = {
        "source": path.name,
        "encodingSource": "CP932",
        "convertedAt": date.today().isoformat(),
    }
    if groups and (not preferTables or not tables):
        payload["groups"] = groups
    if tables:
        payload["tables"] = tables
        # detectors は TableList の UI/処理メタとしても使える
        payload["detectors"] = [
            {
                "id": t["id"],
                "kind": t["id"],
                "channels": t.get("channels", []),
            }
            for t in tables
            if t.get("id") in {"Ha", "DM", "NL", "VCC"}
        ]
    return payload


def main() -> None:
    """CLI エントリ。"""
    parser = argparse.ArgumentParser(description="Convert GroupList/TableList .inf (CP932) to UTF-8 JSON")
    parser.add_argument("inputs", nargs="+", type=Path, help=".inf ファイル")
    parser.add_argument("-o", "--output", type=Path, default=Path("config"))
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    for path in args.inputs:
        data = parseLooseInf(path)
        if "groups" in data and "tables" not in data:
            out = args.output / "GroupList.json"
        elif "tables" in data and "groups" not in data:
            out = args.output / "TableList.json"
        elif "table" in path.name.lower():
            out = args.output / "TableList.json"
        else:
            out = args.output / "GroupList.json"
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
