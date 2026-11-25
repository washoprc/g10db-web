# g10db-web

GAMMA 10/PDX 実験データ閲覧システム **g10db** の PHP 実装（`G10DB` + `TekeTekeKun`）を、**FastAPI + React (Vite + Plotly) + nginx** に再構築した後継です。

現行の `washoprc/docker-g10db`（PHP コンテナ）は変更しません。本リポジトリは学内 Docker（`shared` ネットワーク + nginx-proxy）向けの並行デプロイを想定します。

## 目的

- ショット検索（最新 / 番号 / 日付・最寄り日付フォールバック）を REST API と React UI で提供
- 診断波形 **Ha / DM / NL / VCC** を FTP + readshot パース + 校正後処理で表示（旧 jpgraph 相当を Plotly 化）
- `GroupList.inf` / `TableList.inf`（CP932）を UTF-8 JSON 化し、`Ha_coef` / `NL` を `config/` に配置
- **任意 SQL（旧 `arb.php`）は提供しない**（固定クエリ + プレースホルダのみ）
- Basic 認証は未導入（入口は認証なしで公開）

## 構成

```text
backend/          FastAPI（ショット・波形 API）
frontend/         React + Vite + Plotly
nginx/            /api プロキシ + SPA（Basic 認証は未導入）
config/           GroupList.json / TableList.json / Ha_coef / NL
scripts/          .inf → JSON 変換、旧ツリー同期
docker-compose.yml
```

## 起動（学内 LAN・推奨）

`130.158.92.0/24` から到達できるよう、HTTP を全インタフェース（`0.0.0.0:8080`）に公開します。  
外部ネットワーク `shared` や `VIRTUAL_HOST` は不要です。

```bash
cp .env.example .env
# USE_DEMO=0、DB_PASSWORD / FTP_* を設定
docker compose up -d --build
```

ブラウザ（このホストが `130.158.92.11` の場合）:

- http://130.158.92.11:8080
- http://130.158.92.11:8080/docs
- http://130.158.92.11:8080/api/health

`localhost:8080` でも同一ホストからは開けます。Basic 認証はまだかけていません。

特定 NIC だけに縛る場合は `.env` で:

```bash
HOST_BIND_IP=130.158.92.11
HOST_HTTP_PORT=8080
```

### 波形（本番・kasumi FTP）

`USE_DEMO=0` のとき、波形は kasumi 上のポートファイルから取得します。

| 項目 | 値 |
| --- | --- |
| ホスト | `FTP_HOST=130.158.92.4` |
| ユーザ | `FTP_USER=mwls` |
| パスワード | `FTP_PASSWORD`（`.env` のみ・コミット禁止） |
| ベースパス | `FTP_BASE_PATH=/usr2/shot` |
| リモートパス | `/usr2/shot/{shotNo}/{port}`（**拡張子なし**、Ha/DM サブディレクトリなし） |

ポート名の解決:

- **Ha**: `config/Ha_coef/{detector}/port.txt`（ショット適合 / read_fit_shot）
- **NL**: `config/NL/{channel}.txt` の channelA / channelB
- **DM**: `DM_CC` → `DMC500`、`DM_A` → `DMC600`
- **VCC**: `VCCC00`

バイナリは CAMAC readshot 互換（160 バイトヘッダ + BE uint16/uint8）。後処理は TekeTekeKun 準拠です。

- **Ha**: HaGraph 式 `(data-max-bg)/max*5000*coef`（coef は calc_1/calc_2）
- **DM**: DMGraph 式（DMC500+DMC600 リップル補正→積分）
- **NL**: NLupGraph2 式（2 ポート atan2 位相アンラップ）
- **VCC**: VCCGraph 式（bipolar × camac_range/unit）

取得失敗時はデモ波形にフォールバックし、`note` を返します。診断は `/api/waveforms/meta/status` と `/api/waveforms/{shotNo}/diagnose`。

### 学内 Docker（nginx-proxy + shared）

前提: `docker network create shared` 済み。

```bash
cp .env.example .env
# USE_DEMO=0、DB_PASSWORD / FTP_* を設定
# VIRTUAL_HOST 等は docker-compose.campus.yml 側のデフォルトを利用
docker compose -f docker-compose.yml -f docker-compose.campus.yml up -d --build
```

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
| GET | `/api/waveforms/{shotNo}/{kind}` | Ha/DM/NL/VCC（省略時窓は long: 50–450 / short: 50–250） | TekeTekeKun |
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

- Basic 認証は未導入。入口は `auth_basic off`
- クライアント IP は、接続元が Docker 上のプロキシ網のときだけ `X-Forwarded-For` から復元する

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
