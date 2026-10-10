import { defineConfig } from 'vite';

export default defineConfig({
  // relative base so appassets.androidplatform.net/assets/index.html resolves its assets
  base: './',
  build: {
    outDir: 'dist',
    target: 'es2020',
  },
});
