"""g10db-web FastAPI エントリポイント。

旧 PHP (G10DB + TekeTekeKun) の主要機能を REST API として再構築する。
任意 SQL（旧 arb.php）はセキュリティ上提供しない。
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import getSettings
from app.routers import health, shots, waveforms

settings = getSettings()

app = FastAPI(
    title="g10db-web API",
    description=(
        "GAMMA 10/PDX 実験ショット・波形閲覧 API。"
        "PHP g10db からの移行実装。"
    ),
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.corsOriginList,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(shots.router, prefix="/api")
app.include_router(waveforms.router, prefix="/api")


@app.get("/")
def root() -> dict[str, str]:
    """ルート。API ドキュメントへの案内。"""
    return {"service": "g10db-web", "docs": "/docs"}
