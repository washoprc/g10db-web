#!/bin/sh
# nginx を起動する。Basic 認証はまだ使わない。
set -eu

exec nginx -g 'daemon off;'
