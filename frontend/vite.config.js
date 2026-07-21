import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

// Built assets are emitted into the Python package's static/ directory
// and served by the FastAPI app; base matches the /static mount.
export default defineConfig({
  plugins: [vue()],
  base: "/static/",
  build: {
    outDir: "../transitio_editor/static",
    emptyOutDir: true,
  },
});
