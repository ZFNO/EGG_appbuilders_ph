import { defineConfig } from 'vite';

export default defineConfig({
  base: './',
  server: { port: 5181, open: true },
  build: { outDir: 'dist' }
});
