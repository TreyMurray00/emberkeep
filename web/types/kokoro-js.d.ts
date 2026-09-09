declare module 'kokoro-js' {
  export const env: {
    wasmPaths:
      | string
      | Record<string, string>;
  };

  export class KokoroTTS {
    static from_pretrained(model: string, options?: Record<string, unknown>): Promise<KokoroTTS>;
    generate(text: string, options?: Record<string, unknown>): Promise<{ toBlob(): Blob }>;
  }
}
