import { describe, expect, it } from "vitest";
import { previewPath } from "./preview";

describe('preview isolation', () => {
  const origin = 'http://127.0.0.1:8765';
  it('opens only same-origin current-chat preview routes', () => {
    expect(previewPath('/api/sessions/abc/preview/dist/index.html', 'abc', origin)).toBe('/api/sessions/abc/preview/dist/index.html');
    expect(previewPath(origin + '/api/sessions/abc/preview/index.html', 'abc', origin)).toBe('/api/sessions/abc/preview/index.html');
  });
  it('rejects other chats, origins, API routes, and active schemes', () => {
    for (const value of ['/api/sessions/xyz/preview/index.html', 'https://example.com/api/sessions/abc/preview/index.html', '/api/sessions/abc/preview/../../turns', 'javascript:alert(1)', '/api/health']) {
      expect(previewPath(value, 'abc', origin)).toBeNull();
    }
  });
});
