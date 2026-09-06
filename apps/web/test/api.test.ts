import { describe, expect, test } from "bun:test";

import { api, normalizeNews } from "../src/api";

describe("news API normalization", () => {
  test("turns label mutation responses into the same UI shape as list results", () => {
    const item = normalizeNews({
      id: "news-1",
      title: "Synthetic",
      body_md: "Body",
      source: "rss",
      language: "ru",
      labels: [
        { facet: "priority", value: "high", origin: "manual", confidence: 1 },
      ],
    });

    expect(item.source_key).toBe("rss");
    expect(item.lang).toBe("ru");
    expect(item.effective).toEqual({ priority: ["high"] });
    expect(item.opinions[0]?.origin_key).toBe("manual");
  });

  test("preserves a significant empty manual facet", () => {
    const item = normalizeNews({
      id: "news-2",
      body_md: "Body",
      labels: [],
      manual_facets: ["priority"],
    });

    expect(item.manual_facets).toEqual(["priority"]);
    expect(item.effective).toEqual({});
  });

  test("normalizes the label mutation response before Review renders it", async () => {
    const originalFetch = globalThis.fetch;
    const originalDocument = globalThis.document;
    Object.defineProperty(globalThis, "document", {
      configurable: true,
      value: { cookie: "thirdnews_csrf=csrf-token" },
    });
    globalThis.fetch = (async (_input: RequestInfo | URL, init?: RequestInit) => {
      expect(init?.method).toBe("PUT");
      expect(init?.headers).toMatchObject({ "X-CSRF-Token": "csrf-token" });
      return Response.json({
        id: "news-3",
        body_md: "Body",
        source: "rss",
        language: "ru",
        labels: [
          { facet: "priority", value: "high", origin: "manual", confidence: 1 },
        ],
      });
    }) as typeof fetch;

    try {
      const item = await api.setLabels("news-3", { priority: ["high"] });
      expect(item.effective).toEqual({ priority: ["high"] });
      expect(item.source_key).toBe("rss");
      expect(item.lang).toBe("ru");
    } finally {
      globalThis.fetch = originalFetch;
      Object.defineProperty(globalThis, "document", {
        configurable: true,
        value: originalDocument,
      });
    }
  });
});
