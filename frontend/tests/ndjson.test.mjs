import { test } from 'node:test';
import assert from 'node:assert/strict';
import { consumeNDJSON } from '../src/ndjson.mjs';

function bytes(text) {
  const data = new TextEncoder().encode(text);
  return new ReadableStream({
    start(controller) {
      for (const byte of data) controller.enqueue(new Uint8Array([byte]));
      controller.close();
    },
  });
}

test('buffers arbitrary byte boundaries, UTF-8, blank lines, and final unterminated line', async () => {
  const events = [];
  await consumeNDJSON(bytes('\n{"type":"token","text":"你好 ☕"}\n{"type":"done"}'), event => events.push(event));
  assert.equal(events[0].text, '你好 ☕');
  assert.equal(events[1].type, 'done');
});

test('propagates in-stream provider errors', async () => {
  await assert.rejects(consumeNDJSON(bytes('{"type":"error","message":"Rate limited"}\n'), () => {}), /Rate limited/);
});

test('does not treat a broken connection as a successful result', async () => {
  await assert.rejects(consumeNDJSON(bytes('{"type":"token","text":"partial"}\n'), () => {}), /disconnected/);
});
