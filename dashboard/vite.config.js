import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// GitHub Pages serves this project site under /devops-tracker/, so the
// production build needs that absolute base for assets and the jobs.json
// fetch to resolve. Local dev stays at root.
export default defineConfig(({ command }) => ({
  base: command === "build" ? "/devops-tracker/" : "/",
  plugins: [react()],
}));
