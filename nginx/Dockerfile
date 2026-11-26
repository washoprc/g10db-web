# 入口リバースプロキシ。nginx 1.30.8（2026-11-23 セキュリティリリース）。
# Basic 認証の htpasswd は apache2-utils で、起動時に環境変数から生成する。
# パスワードはイメージに焼き込まない。
FROM nginx:1.30.8-alpine

RUN apk add --no-cache apache2-utils

COPY default.conf /etc/nginx/conf.d/default.conf
COPY docker-entrypoint.sh /docker-entrypoint-custom.sh
RUN chmod +x /docker-entrypoint-custom.sh

ENTRYPOINT ["/docker-entrypoint-custom.sh"]
