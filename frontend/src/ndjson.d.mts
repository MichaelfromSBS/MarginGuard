export type StreamEvent = { type: string; text?: string; message?: string; mode?: string; usage?: Record<string, unknown> };
export function consumeNDJSON(body: ReadableStream<Uint8Array>, onEvent: (event: StreamEvent) => void): Promise<void>;
