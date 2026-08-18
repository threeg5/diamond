import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  // HostGator CNAME (diamond.fioatech.com) and Render both stay at /.
  base: process.env.VITE_BASE || "/",
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5174,
    strictPort: true,
  },
});
