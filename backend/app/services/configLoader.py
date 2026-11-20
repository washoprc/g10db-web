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


def loadJson(name: str) -> dict[str, Any]:
    """config 配下の JSON を読み込む。"""
    path = configRoot() / name
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as fp:
        data = json.load(fp)
    return data if isinstance(data, dict) else {}


def loadGroupList() -> dict[str, Any]:
    """診断グループ定義（旧 GroupList.inf）。"""
    return loadJson("GroupList.json")


def loadTableList() -> dict[str, Any]:
    """テーブル／チャネル定義（旧 TableList.inf）。"""
    return loadJson("TableList.json")


def listHaCoefFiles() -> list[str]:
    """Ha 校正係数ファイル名の一覧。"""
    directory = configRoot() / "Ha_coef"
    if not directory.is_dir():
        return []
    return sorted(p.name for p in directory.iterdir() if p.is_file())


def listNlFiles() -> list[str]:
    """NL 校正・設定ファイル名の一覧。"""
    directory = configRoot() / "NL"
    if not directory.is_dir():
        return []
    return sorted(p.name for p in directory.iterdir() if p.is_file())


def describeConfig() -> dict[str, Any]:
    """フロント向けの設定サマリ。"""
    return {
        "groups": loadGroupList().get("groups", []),
        "tables": loadTableList().get("tables", []),
        "haCoefFiles": listHaCoefFiles(),
        "nlFiles": listNlFiles(),
    }
