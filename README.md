# g10db-web

GAMMA 10/PDX 実験データ閲覧システム **g10db** の PHP 実装（`G10DB` + `TekeTekeKun`）を、**FastAPI + React (Vite) + nginx** に再構築したスキャフォールドです。

## 目的

- ショット検索（最新 / 番号 / 日付）を REST API と React UI で提供
- 診断波形 **Ha / DM / NL / VCC** を表示（旧 jpgraph 相当）
- `GroupList.inf` / `TableList.inf` を JSON 化し、`Ha_coef` / `NL` 校正を `config/` に配置
- **任意 SQL（旧 `arb.php`）は提供しない**

## 構成

```text
backend/     FastAPI（ショット・波形 API）
frontend/    React + Vite
nginx/       リバースプロキシ設定
config/      GroupList.json / TableList.json / Ha_coef / NL
scripts/     .inf → JSON 変換
```

## 起動（Docker）

```bash
cp .env.example .env
# デモ確認はそのままで可。本番 DB では USE_DEMO=0 と接続情報を設定
docker compose up --build
```

ブラウザで http://localhost:8080 を開きます。

- API ドキュメント: http://localhost:8080/docs
- ヘルスチェック: http://localhost:8080/api/health

## ローカル開発

### API

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
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

Vite は `/api` を `localhost:8000` へプロキシします。

## API 概要

| Method | Path | 説明 | 旧 PHP |
| --- | --- | --- | --- |
| GET | `/api/shots/latest?limit=` | 最新ショット | `last.php` |
| GET | `/api/shots/by-number?start=&limit=` | 番号以降 | `sn.php` |
| GET | `/api/shots/by-date?date=&limit=` | 日付 | （日付検索） |
| GET | `/api/waveforms/{shotNo}/{kind}` | Ha/DM/NL/VCC | TekeTekeKun |
| GET | `/api/waveforms/meta/config` | 設定サマリ | GroupList/TableList |

`limit` は最大 30 です。任意 SQL エンドポイントはありません。

## 設定移行

1. 既存 PHP ツリーから `GroupList.inf` / `TableList.inf` を用意
2. 変換:

```bash
python3 scripts/convertInf.py /path/to/GroupList.inf /path/to/TableList.inf -o config/
```

3. `Ha_coef/` と `NL/` を `config/Ha_coef` / `config/NL` にコピー
4. 波形バイナリ／CSV を `DATA_ROOT/{shotNo}/` に配置（または FTP/NFS 取得層を追加）

## 環境変数

`.env.example` を参照してください。主な項目:

- `DB_*` … PostgreSQL（`gamma10_exp` / `mainview`）
- `USE_DEMO=1` … DB/波形が無い環境向けデモデータ
- `DATA_ROOT` … 波形ファイルルート
- `MAX_SHOT_LIMIT` … 取得件数上限（既定 30）

## コーディング規約

- Python / TypeScript とも **lowerCamelCase** の関数・変数名
- docstring / JSDoc は日本語
- SQL はサービス層の固定クエリのみ（プレースホルダ必須）

## 注意

- プライベートな旧リポジトリ `washoprc/g10db` への参照はこのスキャフォールド作成時に未取得です。本番チャネル定義・校正・列セットは実ファイルで差し替えてください。
- デモモードの波形は物理的に妥当な合成信号です。解析用途には使いません。
