import assert from "node:assert/strict";
import test from "node:test";

import worker from "./index.js";

function staticAssets(requestedPaths) {
  return {
    async fetch(request) {
      const path = new URL(request.url).pathname;
      requestedPaths.push(path);
      return path === "/index.html"
        ? new Response("application", { status: 200 })
        : new Response("missing", { status: 404 });
    },
  };
}

test("serves the SPA entrypoint when a browser route has no static asset", async () => {
  const requestedPaths = [];
  const response = await worker.fetch(new Request("https://site.test/about"), {
    ASSETS: staticAssets(requestedPaths),
  });

  assert.equal(response.status, 200);
  assert.deepEqual(requestedPaths, ["/about", "/index.html"]);
});

test("does not turn a missing non-GET request into the SPA entrypoint", async () => {
  const requestedPaths = [];
  const response = await worker.fetch(
    new Request("https://site.test/api", { method: "POST" }),
    { ASSETS: staticAssets(requestedPaths) },
  );

  assert.equal(response.status, 404);
  assert.deepEqual(requestedPaths, ["/api"]);
});
