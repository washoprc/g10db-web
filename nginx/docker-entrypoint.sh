#!/bin/sh
# Basic 認証ファイルを環境変数から生成して nginx を起動する。
set -eu

HTPASSWD_FILE=/etc/nginx/htpasswd
USER_NAME="${BASIC_AUTH_USER:-g10db}"
USER_PASS="${BASIC_AUTH_PASSWORD:-}"

if [ -z "$USER_PASS" ]; then
  echo "WARNING: BASIC_AUTH_PASSWORD is empty; generating random password for this boot" >&2
  USER_PASS="$(tr -dc 'A-Za-z0-9' </dev/urandom | head -c 16)"
  echo "Generated BASIC_AUTH_PASSWORD=${USER_PASS}" >&2
fi

# openssl passwd -apr1 で htpasswd 互換ハッシュを作る
HASH="$(openssl passwd -apr1 "$USER_PASS")"
printf '%s:%s\n' "$USER_NAME" "$HASH" > "$HTPASSWD_FILE"
chmod 640 "$HTPASSWD_FILE"

exec nginx -g 'daemon off;'
