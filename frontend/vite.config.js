import { defineConfig } from "vite";
import react, { reactCompilerPreset } from "@vitejs/plugin-react";
import babel from "@rolldown/plugin-babel";

// https://vite.dev/config/
export default defineConfig({
  server: {
    host: "0.0.0.0",
    port: 3000,
    strictPort: false,
    allowedHosts: ["garim.shop", "www.garim.shop", "localhost"],
    watch: {
      usePolling: true,
      interval: 500,
    },
  },
  plugins: [react(), babel({ presets: [reactCompilerPreset()] })],
});
