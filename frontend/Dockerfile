# 本番フロントのビルドと配信。
# ビルドは Node.js 22.23.5（2026-11-11 セキュリティリリース）。
# 配信は nginx 1.30.8。依存は package-lock.json を npm ci で固定する。
FROM node:22.23.5-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.30.8-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
