import type { KokoroTTS } from 'kokoro-js';
import ortWasmJsepModuleUrl from '../node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.jsep.mjs?url';
import ortWasmJsepBinaryUrl from '../node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.jsep.wasm?url';
import ortWasmModuleUrl from '../node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.mjs?url';
import ortWasmBinaryUrl from '../node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.wasm?url';
let model: KokoroTTS | null = null;
// Inference lives in a worker so the inventory and HUD stay responsive.
self.onmessage = async (event: MessageEvent) => {
  const { type, id, text, voice } = event.data;
  try {
    if (type === 'load') {
      // phonemizer's browser bundle is built by Emscripten and still reads
      // `window.indexedDB` / `window.location` while initializing. A Web
      // Worker exposes those APIs on globalThis instead, so provide the alias
      // before importing kokoro-js. Without it the import aborts immediately
      // with `window is not defined` and the model download never begins.
      const workerGlobal = globalThis as unknown as {
        window?: typeof globalThis;
      };
      workerGlobal.window ??= globalThis;

      // Keep dependency-import failures inside the error-reporting boundary.
      // kokoro-js is in optimizeDeps.include, so Vite pre-bundles it without
      // HMR injection — safe to import inside a worker.
      const { KokoroTTS, env: kokoroEnv } = await import('kokoro-js');

      // @huggingface/transformers@3.8.1 ships only JSEP WASM files in its
      // dist/ and overrides wasmPaths to its CDN at import time. That CDN
      // path is missing the standard ort-wasm-simd-threaded.{mjs,wasm} files,
      // so device:'wasm' 404s and the model never loads. Point wasmPaths at
      // the locally installed onnxruntime-web dist instead — it ships all
      // variants and is served as a normal static asset by Vite/vinext.
      // Using kokoro-js's own env proxy avoids a direct @huggingface/transformers
      // import, which would arrive with Vite HMR code that crashes in workers.
      kokoroEnv.wasmPaths = {
        'ort-wasm-simd-threaded.jsep.mjs': ortWasmJsepModuleUrl,
        'ort-wasm-simd-threaded.jsep.wasm': ortWasmJsepBinaryUrl,
        'ort-wasm-simd-threaded.mjs': ortWasmModuleUrl,
        'ort-wasm-simd-threaded.wasm': ortWasmBinaryUrl,
      };

      const modelId = 'onnx-community/Kokoro-82M-v1.0-ONNX';
      const progress_callback = (p: { status: string; progress?: number }) => {
        if (p.status === 'progress')
          self.postMessage({
            type: 'progress',
            progress: Math.round(p.progress || 0),
          });
      };
      // WebGPU can be faster, but Kokoro's output is corrupted on some
      // browser/GPU/driver combinations even when initialization succeeds.
      // q8/WASM is slower but produces stable, intelligible narration.
      model = await KokoroTTS.from_pretrained(modelId, {
        dtype: 'q8',
        device: 'wasm',
        progress_callback,
      });

      self.postMessage({ type: 'ready', backend: 'wasm' });
    } else if (type === 'speak' && model) {
      const audio = await model.generate(text, { voice });
      self.postMessage({ type: 'audio', id, blob: audio.toBlob() });
    }
  } catch (error) {
    console.error('Browser narration failed:', error);
    self.postMessage({
      type: 'error',
      id,
      message: type === 'load'
        ? 'Voice model could not load. Check your connection, then turn voice off and on to retry.'
        : 'Speech generation failed. Press Replay to retry; text remains available.',
      detail: error instanceof Error ? error.message : String(error),
    });
  }
};
