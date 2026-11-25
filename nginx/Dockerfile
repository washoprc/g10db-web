# 入口リバースプロキシ。nginx 1.30.8（2026-11-23 セキュリティリリース）。
# Basic 認証は未導入のため htpasswd 用の openssl は入れない。
FROM nginx:1.30.8-alpine

COPY default.conf /etc/nginx/conf.d/default.conf
COPY docker-entrypoint.sh /docker-entrypoint-custom.sh
RUN chmod +x /docker-entrypoint-custom.sh

ENTRYPOINT ["/docker-entrypoint-custom.sh"]
