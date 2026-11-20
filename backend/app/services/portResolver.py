"""FTP ポート名の解決（kasumi `/usr2/shot/{shot}/{port}` 向け）。

Ha は Ha_coef/{detector}/port.txt をショット適合で読み、
NL は NL/{channel}.txt の channelA/channelB、
DM / VCC は固定ポート名を返す。
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

from app.services.configLoader import configRoot
from app.services.processors import parseNlConfig, resolveHaDetectorDir

# DMGraph.php: DMCC は DMC500 + DMC600 のペア
DM_PORT_PAIRS: dict[str, tuple[str, str]] = {
    "DM_CC": ("DMC500", "DMC600"),
    "DMCC": ("DMC500", "DMC600"),
}

# VCC は単一ポート
VCC_PORT = "VCCC00"


def readFitShotRow(
    path: Path,
    shotNo: int | None,
) -> list[str] | None:
    """shot_no 付き CSV から、指定ショット以下で最大の行を返す。

    TekeTekeKun の read_fit_shot 相当。先頭行はヘッダ（shot_no,...）。
    戻り値はショット番号を除いたカラム値のリスト。
    """
    if not path.is_file():
        return None
    rows: list[tuple[int, list[str]]] = []
    text = path.read_text(encoding="utf-8", errors="ignore")
    reader = csv.reader(text.splitlines())
    for parts in reader:
        if not parts:
            continue
        head = parts[0].strip().lower()
        if head in {"shot_no", "shotno", "shot"}:
            continue
        try:
            rowShot = int(float(parts[0]))
        except ValueError:
            continue
        values = [p.strip() for p in parts[1:] if str(p).strip() != ""]
        if values:
            rows.append((rowShot, values))
    if not rows:
        return None
    rows.sort(key=lambda item: item[0])
    if shotNo is None:
        return rows[-1][1]
    chosen = rows[0][1]
    for threshold, values in rows:
        if shotNo >= threshold:
            chosen = values
        else:
            break
    return chosen


def resolveHaPorts(detector: str, shotNo: int | None) -> list[str]:
    """Ha 検出器の port.txt からポート名一覧を返す。"""
    detectorDir = resolveHaDetectorDir(detector)
    if detectorDir is None:
        return []
    ports = readFitShotRow(detectorDir / "port.txt", shotNo)
    if not ports:
        return []
    return [p for p in ports if re.fullmatch(r"[A-Za-z0-9_]+", p)]


def resolveNlPorts(channel: str) -> list[str]:
    """NL 設定ファイルの channelA / channelB をポート名として返す。"""
    nlDir = configRoot() / "NL"
    if not nlDir.is_dir():
        return []
    # 完全一致（拡張子付き／無し）を優先
    candidates: list[Path] = []
    for name in (f"{channel}.txt", channel, f"{channel}.TXT"):
        path = nlDir / name
        if path.is_file():
            candidates.append(path)
    if not candidates:
        candidates = sorted(nlDir.glob(f"{channel}*.txt"))
    for path in candidates:
        if path.name.lower() == "readme.md":
            continue
        meta = parseNlConfig(path)
        ports: list[str] = []
        for key in ("channelA", "channelB"):
            value = meta.get(key)
            if isinstance(value, str) and value.strip():
                ports.append(value.strip())
        return ports
    return []


def resolveDmPorts(channel: str) -> list[str]:
    """DM チャネルのポートペア（無ければ空）。"""
    pair = DM_PORT_PAIRS.get(channel)
    if pair is None:
        return []
    return [pair[0], pair[1]]


def resolveDmPort(channel: str) -> str | None:
    """互換: DM の第 1 ポート名。未定義なら None。"""
    ports = resolveDmPorts(channel)
    return ports[0] if ports else None


def resolveVccPort(_channel: str | None = None) -> str:
    """VCC の固定ポート名（VCCC00）。"""
    return VCC_PORT


def resolvePorts(
    kind: str,
    channel: str,
    shotNo: int | None = None,
) -> list[str]:
    """診断種別・チャネル名から FTP ポート名一覧を返す。"""
    if kind == "Ha":
        return resolveHaPorts(channel, shotNo)
    if kind == "NL":
        return resolveNlPorts(channel)
    if kind == "DM":
        return resolveDmPorts(channel)
    if kind == "VCC":
        return [resolveVccPort(channel)]
    return []
