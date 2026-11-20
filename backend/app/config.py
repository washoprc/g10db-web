"""アプリケーション設定。

環境変数から PostgreSQL / FTP / デモモード等を読み込む。
シークレットは .env のみ（リポジトリにパスワードを置かない）。
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """実行時設定（コード側は lowerCamelCase）。"""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    dbHost: str = "localhost"
    dbPort: int = 5432
    dbName: str = "gamma10_exp"
    dbUser: str = "prc"
    dbPassword: str = ""

    useDemo: bool = True
    dataRoot: Path = Path("/data")
    configRoot: Path = Path("/app/config")
    apiCorsOrigins: str = "*"
    maxShotLimit: int = 30

    ftpHost: str = ""
    ftpPort: int = 21
    ftpUser: str = ""
    ftpPassword: str = ""
    ftpBasePath: str = "/usr2/shot"
    ftpTimeoutSec: int = 30

    @property
    def dsn(self) -> str:
        """psycopg 用接続文字列を返す。"""
        return (
            f"host={self.dbHost} port={self.dbPort} dbname={self.dbName} "
            f"user={self.dbUser} password={self.dbPassword}"
        )

    @property
    def corsOriginList(self) -> list[str]:
        """CORS 許可オリジンの一覧。"""
        if self.apiCorsOrigins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.apiCorsOrigins.split(",") if o.strip()]


class SettingsLoader(BaseSettings):
    """環境変数名を UPPER_SNAKE で受け取るためのローダ。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        populate_by_name=True,
    )

    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "gamma10_exp"
    DB_USER: str = "prc"
    DB_PASSWORD: str = ""
    USE_DEMO: bool = True
    DATA_ROOT: Path = Path("/data")
    CONFIG_ROOT: Path = Path("/app/config")
    API_CORS_ORIGINS: str = "*"
    MAX_SHOT_LIMIT: int = 30
    FTP_HOST: str = ""
    FTP_PORT: int = 21
    FTP_USER: str = ""
    FTP_PASSWORD: str = ""
    FTP_BASE_PATH: str = "/usr2/shot"
    FTP_TIMEOUT_SEC: int = 30

    def toSettings(self) -> Settings:
        """lowerCamelCase の Settings に変換する。"""
        return Settings(
            dbHost=self.DB_HOST,
            dbPort=self.DB_PORT,
            dbName=self.DB_NAME,
            dbUser=self.DB_USER,
            dbPassword=self.DB_PASSWORD,
            useDemo=self.USE_DEMO,
            dataRoot=self.DATA_ROOT,
            configRoot=self.CONFIG_ROOT,
            apiCorsOrigins=self.API_CORS_ORIGINS,
            maxShotLimit=self.MAX_SHOT_LIMIT,
            ftpHost=self.FTP_HOST,
            ftpPort=self.FTP_PORT,
            ftpUser=self.FTP_USER,
            ftpPassword=self.FTP_PASSWORD,
            ftpBasePath=self.FTP_BASE_PATH,
            ftpTimeoutSec=self.FTP_TIMEOUT_SEC,
        )


@lru_cache
def getSettings() -> Settings:
    """プロセス内で共有する設定インスタンスを返す。"""
    return SettingsLoader().toSettings()
