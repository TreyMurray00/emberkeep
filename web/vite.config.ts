import { sites } from '@openai/sites-vite-plugin';
import tailwindcss from '@tailwindcss/postcss';
import vinext from 'vinext';
import { defineConfig } from 'vite';
export default defineConfig({
  // Kokoro resolves its voice assets through import.meta.url in the worker.
  worker: { format: 'es' },
  // Prepare the speech dependency at startup rather than invalidating worker
  // imports when a player enables voice for the first time.
  optimizeDeps: { include: ['kokoro-js'] },
  css: { postcss: { plugins: [tailwindcss()] } },
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    proxy: { '/api': { target: 'http://0.0.0.0:8000' } },
  },
  plugins: [vinext(), sites()],
});
