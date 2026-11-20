import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

/** Vite 開発サーバ設定。/api は FastAPI へプロキシする。 */
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
