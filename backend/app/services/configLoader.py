"""GroupList / TableList / 校正ファイルの読込。

PHP 版 TekeTekeKun が参照していた GroupList.inf / TableList.inf を
JSON に変換したものを読み込む。Ha_coef と NL 校正は config 配下に配置する。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import getSettings


def configRoot() -> Path:
    """設定ルートディレクトリ。"""
    return getSettings().configRoot


def loadJson(name: str) -> dict[str, Any] | list[Any]:
    """config 配下の JSON を読み込む。"""
    path = configRoot() / name
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as fp:
        data = json.load(fp)
    if isinstance(data, (dict, list)):
        return data
    return {}


def loadJsonObject(name: str) -> dict[str, Any]:
    """オブジェクト JSON のみを返す（配列なら空 dict）。"""
    data = loadJson(name)
    return data if isinstance(data, dict) else {}


def loadGroupList() -> dict[str, Any]:
    """診断グループ定義（波形用 GroupList.json）。"""
    return loadJsonObject("GroupList.json")


def loadTableList() -> dict[str, Any]:
    """テーブル／チャネル定義（波形用 TableList.json）。"""
    return loadJsonObject("TableList.json")


def loadG10dbGroups() -> list[Any]:
    """G10DB ShowTable 用グループ定義（group_list.json）。"""
    data = loadJson("group_list.json")
    return data if isinstance(data, list) else []


def loadG10dbTableMap() -> dict[str, Any]:
    """G10DB テーブル定義を tableName → def の辞書で返す（table_list.json）。"""
    data = loadJson("table_list.json")
    if not isinstance(data, list):
        return {}
    result: dict[str, Any] = {}
    for entry in data:
        if isinstance(entry, dict):
            name = entry.get("tableName")
            if isinstance(name, str) and name:
                result[name] = entry
    return result


def listHaCoefFiles() -> list[str]:
    """Ha 校正エントリ（検出器ディレクトリ名 + 直下ファイル）の一覧。"""
    directory = configRoot() / "Ha_coef"
    if not directory.is_dir():
        return []
    names: list[str] = []
    for path in sorted(directory.iterdir()):
        if path.name.lower() in {"readme.md", ".gitkeep"}:
            continue
        if path.is_dir() or path.is_file():
            names.append(path.name)
    return names


def listNlFiles() -> list[str]:
    """NL 校正・設定ファイル名の一覧。"""
    directory = configRoot() / "NL"
    if not directory.is_dir():
        return []
    return sorted(
        p.name
        for p in directory.iterdir()
        if p.is_file() and p.name.lower() not in {"readme.md", ".gitkeep"}
    )


def describeConfig() -> dict[str, Any]:
    """フロント向けの設定サマリ。"""
    g10Groups = loadJson("group_list.json")
    g10Tables = loadJson("table_list.json")
    return {
        "groups": loadGroupList().get("groups", []),
        "tables": loadTableList().get("tables", []),
        "detectors": loadTableList().get("detectors", []),
        "haCoefFiles": listHaCoefFiles(),
        "nlFiles": listNlFiles(),
        "g10dbGroupCount": len(g10Groups) if isinstance(g10Groups, list) else 0,
        "g10dbTableCount": len(g10Tables) if isinstance(g10Tables, list) else 0,
        "syncedFromLegacy": True,
    }
