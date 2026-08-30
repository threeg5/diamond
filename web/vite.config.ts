import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  return {
    // HostGator folder is /thediamond/. Local and Render stay at /.
    base: env.VITE_BASE || "/",
    plugins: [react()],
    server: {
      host: "127.0.0.1",
      port: 5174,
      strictPort: true,
      proxy: {
        "/tpe-api": {
          target: process.env.VITE_TPE_API_URL || "http://127.0.0.1:8010",
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/tpe-api/, ""),
        },
      },
    },
  };
});
