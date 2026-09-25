import { defineConfig } from "astro/config";

export default defineConfig({
  output: "static",
  build: {
    format: "directory",
    inlineStylesheets: "never",
  },
  compressHTML: true,
});
