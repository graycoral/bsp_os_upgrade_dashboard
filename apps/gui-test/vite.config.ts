import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';
const local = (path: string) => fileURLToPath(new URL(path, import.meta.url));

// Build only the standalone GUI. Dashboard output lives in apps/web/dist.
export default defineConfig({
  root: local('.'),
  plugins: [react()],
  resolve: {
    dedupe: ['react', 'react-dom'],
    alias: { react: local('./node_modules/react'), 'react-dom': local('./node_modules/react-dom') },
  },
  build: {
    outDir: local('./static'),
    emptyOutDir: true,
  },
});
