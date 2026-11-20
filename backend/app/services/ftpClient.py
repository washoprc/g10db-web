"""FTP 経由でショット波形バイナリを取得する。

TekeTekeKun/ftp.php 相当。Passive モード必須（Docker 環境向け）。
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


def ensureLocalCacheDir(shotNo: int) -> Path:
    """ショット単位のローカルキャッシュディレクトリを確保する。"""
    cacheRoot = getSettings().dataRoot / "ftp_cache"
    shotDir = cacheRoot / str(shotNo)
    shotDir.mkdir(parents=True, exist_ok=True)
    return shotDir


def fetchShotFiles(shotNo: int, remoteSubdir: str, channelNames: list[str]) -> list[Path]:
    """指定ショットのチャネルファイルを FTP から取得する。

    Args:
        shotNo: ショット番号
        remoteSubdir: リモート上の診断サブディレクトリ（Ha / DM / NL / VCC）
        channelNames: 取得するチャネル名

    Returns:
        ローカルに保存したファイルパス一覧（取得できたもののみ）
    """
    settings = getSettings()
    if not isFtpConfigured():
        return []

    localDir = ensureLocalCacheDir(shotNo) / remoteSubdir
    localDir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []

    try:
        with ftplib.FTP() as ftp:
            ftp.connect(settings.ftpHost, settings.ftpPort, timeout=settings.ftpTimeoutSec)
            ftp.login(settings.ftpUser, settings.ftpPassword)
            ftp.set_pasv(True)
            remoteBase = settings.ftpBasePath.rstrip("/")
            for channel in channelNames:
                remoteName = f"{channel}.dat"
                remotePath = f"{remoteBase}/{shotNo}/{remoteSubdir}/{remoteName}"
                localPath = localDir / remoteName
                if localPath.exists() and localPath.stat().st_size > 0:
                    saved.append(localPath)
                    continue
                try:
                    with localPath.open("wb") as fp:
                        ftp.retrbinary(f"RETR {remotePath}", fp.write)
                    if localPath.stat().st_size > 0:
                        saved.append(localPath)
                    else:
                        localPath.unlink(missing_ok=True)
                except ftplib.error_perm as exc:
                    logger.info("FTP miss %s: %s", remotePath, exc)
                    localPath.unlink(missing_ok=True)
    except (OSError, ftplib.all_errors) as exc:
        logger.warning("FTP fetch failed for shot %s: %s", shotNo, exc)
        return saved

    return saved
