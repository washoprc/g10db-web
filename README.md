# g10db-web

GAMMA 10/PDX 実験データ閲覧システム **g10db** の PHP 実装（`G10DB` + `TekeTekeKun`）を、**FastAPI + React (Vite + Plotly) + nginx** に再構築した後継です。

現行の `washoprc/docker-g10db`（PHP コンテナ）は変更しません。本リポジトリは学内 Docker（`shared` ネットワーク + nginx-proxy）向けの並行デプロイを想定します。

## 目的

- ショット検索（最新 / 番号 / 日付・最寄り日付フォールバック）を REST API と React UI で提供
- 診断波形 **Ha / DM / NL / VCC** を FTP + readshot パース + 校正後処理で表示（旧 jpgraph 相当を Plotly 化）
- `GroupList.inf` / `TableList.inf`（CP932）を UTF-8 JSON 化し、`Ha_coef` / `NL` を `config/` に配置
- **任意 SQL（旧 `arb.php`）は提供しない**（固定クエリ + プレースホルダのみ）
- 学内 `130.158.92.0/24` は認証なし、学外は Basic 認証

## 構成

```text
backend/          FastAPI（ショット・波形 API）
frontend/         React + Vite + Plotly
nginx/            学内 IP 許可 + Basic 認証 + /api プロキシ + SPA
config/           GroupList.json / TableList.json / Ha_coef / NL
scripts/          .inf → JSON 変換、旧ツリー同期
docker-compose.yml
```

## 起動（学内 Docker）

前提: nginx-proxy 用の外部ネットワーク `shared` が存在する。

```bash
cp .env.example .env
# DB_PASSWORD / FTP_* / BASIC_AUTH_PASSWORD を設定
# USE_DEMO=0 で本番
docker compose up -d --build
```

`VIRTUAL_HOST=g10db.prc.tsukuba.ac.jp` により nginx-proxy が TLS 終端します。

### ローカル（shared が無い場合）

```bash
cp .env.example .env
# USE_DEMO=1
docker compose -f docker-compose.yml -f docker-compose.local.yml up --build
```

ブラウザ: http://localhost:8080  
API docs: http://localhost:8080/docs  
Health: http://localhost:8080/api/health

## ローカル開発

### API

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export USE_DEMO=1 CONFIG_ROOT=../config
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## API 概要

| Method | Path | 説明 | 旧 PHP |
| --- | --- | --- | --- |
| GET | `/api/shots/latest?limit=` | 最新ショット | `last.php` |
| GET | `/api/shots/by-number?start=&limit=` | 番号以降 | `sn.php` |
| GET | `/api/shots/by-date?date=&limit=` | 日付（無ければ最寄り） | `day.php` |
| GET | `/api/waveforms/{shotNo}/{kind}` | Ha/DM/NL/VCC | TekeTekeKun |
| GET | `/api/waveforms/meta/config` | 設定サマリ | GroupList/TableList |

`limit` は最大 **30**。任意 SQL エンドポイントはありません。

## 旧 PHP からの設定取り込み

`washoprc/g10db`（または docker-g10db の `g10db/`）が手元にある場合:

```bash
./scripts/syncFromLegacy.sh /path/to/g10db
```

手動の場合:

```bash
python3 scripts/convertInf.py /path/to/G10DB/GroupList.inf /path/to/G10DB/TableList.inf -o config/
cp -a /path/to/TekeTekeKun/Ha_coef/. config/Ha_coef/
cp -a /path/to/TekeTekeKun/NL/. config/NL/
```

実データは `config/Ha_coef/`（HaCT / HaEB / HaWB 等）、`config/NL/`、
`config/group_list.json` / `config/table_list.json`（G10DB 本体）に取り込み済みです。
追加更新は `./scripts/syncFromLegacy.sh` または親エージェントの `g10db-web-config.tgz` で行います。

## 認証モデル

- nginx が `X-Forwarded-For` からクライアント IP を復元
- `130.158.92.0/24`（およびプライベートレンジ）は Basic 認証オフ
- それ以外は `BASIC_AUTH_USER` / `BASIC_AUTH_PASSWORD`（`.env` のみ）

## コーディング規約

- Python / TypeScript とも **lowerCamelCase** の関数・変数名
- docstring / JSDoc は日本語
- SQL はサービス層の固定クエリのみ（プレースホルダ必須）

## テスト

```bash
cd backend
pip install -r requirements.txt
USE_DEMO=1 CONFIG_ROOT=../config pytest -q
```
