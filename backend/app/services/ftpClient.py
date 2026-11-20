"""FTP 経由でショット波形バイナリを取得する。

TekeTekeKun/ftp.php 相当（kasumi: `/usr2/shot/{shot}/{port}`）。
パスに拡張子も診断サブディレクトリ（Ha/DM 等）も付けない。
Passive モード必須（Docker 環境向け）。
認証情報は環境変数のみから読み、リポジトリには置かない。
"""

from __future__ import annotations

import ftplib
import logging
from pathlib import Path

from app.config import getSettings

logger = logging.getLogger(__name__)


def isFtpConfigured() -> bool:
    """FTP 接続に必要な設定が揃っているか。"""
    settings = getSettings()
    return bool(settings.ftpHost and settings.ftpUser)


def ftpConfigStatus() -> dict[str, object]:
    """FTP 設定の要約（パスワード値は返さない）。"""
    settings = getSettings()
    return {
        "host": settings.ftpHost,
        "user": settings.ftpUser,
        "passwordSet": bool(settings.ftpPassword),
        "basePath": settings.ftpBasePath,
        "port": settings.ftpPort,
        "configured": isFtpConfigured(),
    }


def probeFtpConnection() -> dict[str, object]:
    """FTP に接続・ログインし basePath へ cwd できるか確認する。"""
    settings = getSettings()
    if not isFtpConfigured():
        return {"ok": False, "error": "FTP host/user not configured"}
    try:
        with ftplib.FTP() as ftp:
            ftp.connect(settings.ftpHost, settings.ftpPort, timeout=settings.ftpTimeoutSec)
            ftp.login(settings.ftpUser, settings.ftpPassword)
            ftp.set_pasv(True)
            base = settings.ftpBasePath.rstrip("/") or "/"
            ftp.cwd(base)
        return {"ok": True, "error": None}
    except (OSError, ftplib.all_errors) as exc:
        return {"ok": False, "error": str(exc)}


def ensureLocalCacheDir(shotNo: int) -> Path:
    """ショット単位のローカルキャッシュディレクトリを確保する。"""
    cacheRoot = getSettings().dataRoot / "ftp_cache"
    shotDir = cacheRoot / str(shotNo)
    shotDir.mkdir(parents=True, exist_ok=True)
    return shotDir


def remotePortPath(shotNo: int, portName: str) -> str:
    """リモート上のポートファイルパス（拡張子なし）。"""
    settings = getSettings()
    base = settings.ftpBasePath.rstrip("/")
    return f"{base}/{shotNo}/{portName}"


def fetchPortFile(shotNo: int, portName: str) -> Path | None:
    """1 ポート分のファイルを FTP から取得する。

    リモート: `{FTP_BASE_PATH}/{shotNo}/{portName}`（`.dat` なし、サブディレクトリなし）
    ローカル: `{DATA_ROOT}/ftp_cache/{shotNo}/{portName}`

    Returns:
        取得できたローカルパス。失敗時は None。
    """
    settings = getSettings()
    if not isFtpConfigured() or not portName:
        return None

    localDir = ensureLocalCacheDir(shotNo)
    localPath = localDir / portName
    if localPath.exists() and localPath.stat().st_size > 0:
        return localPath

    remotePath = remotePortPath(shotNo, portName)
    try:
        with ftplib.FTP() as ftp:
            ftp.connect(settings.ftpHost, settings.ftpPort, timeout=settings.ftpTimeoutSec)
            ftp.login(settings.ftpUser, settings.ftpPassword)
            ftp.set_pasv(True)
            with localPath.open("wb") as fp:
                ftp.retrbinary(f"RETR {remotePath}", fp.write)
        if localPath.stat().st_size > 0:
            return localPath
        localPath.unlink(missing_ok=True)
        return None
    except (OSError, ftplib.all_errors) as exc:
        logger.info("FTP miss %s: %s", remotePath, exc)
        localPath.unlink(missing_ok=True)
        return None


def fetchPortFiles(shotNo: int, portNames: list[str]) -> dict[str, Path]:
    """複数ポートを取得し、ポート名 → ローカルパスの辞書を返す。"""
    settings = getSettings()
    if not isFtpConfigured():
        return {}

    saved: dict[str, Path] = {}
    pending = []
    localDir = ensureLocalCacheDir(shotNo)
    for portName in portNames:
        if not portName:
            continue
        localPath = localDir / portName
        if localPath.exists() and localPath.stat().st_size > 0:
            saved[portName] = localPath
        else:
            pending.append(portName)

    if not pending:
        return saved

    try:
        with ftplib.FTP() as ftp:
            ftp.connect(settings.ftpHost, settings.ftpPort, timeout=settings.ftpTimeoutSec)
            ftp.login(settings.ftpUser, settings.ftpPassword)
            ftp.set_pasv(True)
            base = settings.ftpBasePath.rstrip("/")
            for portName in pending:
                remotePath = f"{base}/{shotNo}/{portName}"
                localPath = localDir / portName
                try:
                    with localPath.open("wb") as fp:
                        ftp.retrbinary(f"RETR {remotePath}", fp.write)
                    if localPath.stat().st_size > 0:
                        saved[portName] = localPath
                    else:
                        localPath.unlink(missing_ok=True)
                except ftplib.error_perm as exc:
                    logger.info("FTP miss %s: %s", remotePath, exc)
                    localPath.unlink(missing_ok=True)
    except (OSError, ftplib.all_errors) as exc:
        logger.warning("FTP fetch failed for shot %s: %s", shotNo, exc)

    return saved
