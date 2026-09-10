import { afterEach, expect, it, vi } from "vitest";
import { PlaybackQueue } from "./playback";

afterEach(() => vi.unstubAllGlobals());

it("orders PCM packets, ignores duplicates and stops scheduled audio", () => {
  const samples: number[] = [];
  const stop = vi.fn();
  vi.stubGlobal("AudioContext", class {
    currentTime = 0;
    destination = {};
    createBuffer(_channels: number, length: number, rate: number) {
      const data = new Float32Array(length);
      return { duration: length / rate, getChannelData: () => data, data };
    }
    createBufferSource() {
      return { buffer: null as null | { data: Float32Array }, connect() {}, addEventListener() {}, stop,
        start() { samples.push(this.buffer!.data[0]); } };
    }
  });
  const queue = new PlaybackQueue();
  queue.enqueue(new Int16Array([200]).buffer, "audio/pcm", 2, 24000);
  expect(samples).toEqual([]);
  queue.enqueue(new Int16Array([100]).buffer, "audio/pcm", 1, 24000);
  queue.enqueue(new Int16Array([100]).buffer, "audio/pcm", 1, 24000);
  expect(samples).toEqual([100 / 32768, 200 / 32768]);
  queue.clear();
  expect(stop).toHaveBeenCalledTimes(2);
  queue.enqueue(new Int16Array([300]).buffer, "audio/pcm", 1, 24000);
  expect(samples.at(-1)).toBe(300 / 32768);
});
