# g10db-web

GAMMA 10/PDX 実験データ閲覧システム **g10db** の PHP 実装（`G10DB` + `TekeTekeKun`）を、**FastAPI + React (Vite + Plotly) + nginx** に再構築した後継です。

現行の `washoprc/docker-g10db`（PHP コンテナ）は変更しません。本リポジトリは学内 Docker（`shared` ネットワーク + nginx-proxy）向けの並行デプロイを想定します。

## 目的

- ショット検索（最新 / 番号 / 日付・最寄り日付フォールバック）を REST API と React UI で提供
- 診断波形 **Ha / DM / NL / VCC** を FTP + readshot パース + 校正後処理で表示（旧 jpgraph 相当を Plotly 化）
- `GroupList.inf` / `TableList.inf`（CP932）を UTF-8 JSON 化し、`Ha_coef` / `NL` を `config/` に配置
- **任意 SQL（旧 `arb.php`）は提供しない**（固定クエリ + プレースホルダのみ）
- 入口は Basic 認証。`130.158.92.0/24` だけパスワード不要。検索エンジンにはインデックスさせない

## 構成

```text
backend/          FastAPI（ショット・波形 API）
frontend/         React + Vite + Plotly
nginx/            /api プロキシ + SPA（学内 IP 免除の Basic 認証、noindex）
config/           GroupList.json / TableList.json / Ha_coef / NL
scripts/          .inf → JSON 変換、旧ツリー同期
docker-compose.yml
```

## 起動（学内 LAN）

`130.158.92.0/24` から到達できるよう、HTTP を全インタフェース（`0.0.0.0:8080`）に公開します。  
外部ネットワーク `shared` や `VIRTUAL_HOST` は不要です。

```bash
cp .env.example .env
# USE_DEMO=0、DB_PASSWORD / FTP_* / BASIC_AUTH_PASSWORD を設定
docker compose up -d --build
```

`BASIC_AUTH_PASSWORD` が空だと入口 nginx は起動しません。  
`130.158.92.0/24` からのアクセスはパスワードを聞きません。それ以外（このサーバの `127.0.0.1` を含む）は Basic 認証です。

ブラウザ（このホストが `130.158.92.11` の場合）:

- http://130.158.92.11:8080
- http://130.158.92.11:8080/docs
- http://130.158.92.11:8080/api/health

このホストではポート `8080` を現行 PHP（`docker-g10db`）が使用しています。同じポートでは起動できません。本番は次の HTTPS 手順を使います。

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

### 本番 HTTPS（既存 nginx-proxy + shared）

公開 URL は `https://g10db2.prc.tsukuba.ac.jp` です。  
証明書と振り分けは、すでに動いている nginx-proxy / acme-companion が行います。`docker-g10db` と `shared` のファイルは変更しません。

前提:

- ネットワーク `shared` が存在する
- DNS の `g10db2.prc.tsukuba.ac.jp` がこのホストを向いている
- `VIRTUAL_HOST` を現行 PHP の `g10db.prc.tsukuba.ac.jp` にしない

```bash
cp .env.example .env
# USE_DEMO=0、DB_PASSWORD / FTP_* / BASIC_AUTH_PASSWORD を設定
# VIRTUAL_HOST 等は .env.example の g10db2 を使う
docker compose -f docker-compose.yml -f docker-compose.campus.yml up -d --build
```

この起動ではホストポートを公開しません。`shared` に参加するのは入口 `nginx` だけです。`api` と `web` はプロジェクト内部ネットワークに残し、他コンテナから認証を迂回できないようにします。`LETSENCRYPT_EMAIL` の既定は `washo@prc.tsukuba.ac.jp` で、`.env` から変えられます。

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

## 認証と検索回避

- `130.158.92.0/24` はパスワード不要。それ以外は Basic 認証（`satisfy any`）
- クライアント IP は、接続元が Docker 上のプロキシ網のときだけ `X-Forwarded-For` から復元する。直アクセスの偽装ヘッダは採用しない
- 全応答に `X-Robots-Tag: noindex, nofollow, noarchive` を付ける。HTML にも同じ meta がある
- `/robots.txt` だけ認証の外で `Disallow: /` を返す。学外のクローラは本文を取得する前に認証で止まる
- プロキシの `NETWORK_ACCESS=internal` は使わない。学外を 403 にするとパスワードで通れない

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
