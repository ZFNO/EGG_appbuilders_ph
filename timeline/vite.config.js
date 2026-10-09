import { defineConfig } from 'vite';

export default defineConfig({
  // relative base so dist/ works from any subpath
  base: './',
  server: { port: 5180, open: true },
  build: { outDir: 'dist', assetsDir: 'assets' }
});
