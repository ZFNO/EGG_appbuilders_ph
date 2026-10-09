import { defineConfig } from 'vite';

export default defineConfig({
  // relative base so file:///android_asset/index.html resolves its assets
  base: './',
  server: { port: 5182, open: true },
  build: { outDir: 'dist' }
});
