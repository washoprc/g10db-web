#!/bin/sh
# g10db-web 入口 nginx の起動スクリプト。
#
# 概要:
#   BASIC_AUTH_USER と BASIC_AUTH_PASSWORD から htpasswd を作り、nginx を前景で起動する。
# 主な仕様:
#   - 学内 130.158.92.0/24 の免除は nginx 設定側で行う。このスクリプトはパスワードファイルだけを用意する。
#   - パスワードは標準入力で htpasswd に渡し、プロセス引数には出さない。
# 制限:
#   - ユーザ名またはパスワードが空なら起動しない。
#   - ログとエラーメッセージにパスワードの値は出さない。
#   - htpasswd はコンテナ内だけに作り、リポジトリには置かない。
set -eu
set -o pipefail

htpasswdPath="/etc/nginx/htpasswd"
authUser="${BASIC_AUTH_USER:-}"
authPassword="${BASIC_AUTH_PASSWORD:-}"

if [ -z "${authUser}" ]; then
    echo "docker-entrypoint: BASIC_AUTH_USER が空です。起動を中止します。関数=docker-entrypoint 引数=BASIC_AUTH_USER=(empty) htpasswdPath=${htpasswdPath}" >&2
    exit 1
fi

if [ -z "${authPassword}" ]; then
    echo "docker-entrypoint: BASIC_AUTH_PASSWORD が空です。起動を中止します。関数=docker-entrypoint 引数=BASIC_AUTH_USER=${authUser} BASIC_AUTH_PASSWORD=(empty) htpasswdPath=${htpasswdPath}" >&2
    exit 1
fi

if ! printf '%s\n' "${authPassword}" | htpasswd -ci "${htpasswdPath}" "${authUser}"; then
    echo "docker-entrypoint: htpasswd の生成に失敗しました。関数=docker-entrypoint 引数=BASIC_AUTH_USER=${authUser} htpasswdPath=${htpasswdPath}" >&2
    exit 1
fi

chown root:nginx "${htpasswdPath}"
chmod 640 "${htpasswdPath}"

exec nginx -g 'daemon off;'
