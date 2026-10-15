"use strict";
const test = require("node:test"),
  assert = require("node:assert/strict"),
  fs = require("node:fs"),
  vm = require("node:vm");
const demo = require("../src/pkjs/demo"),
  wire = require("../src/pkjs/wire");
function harness(config, cache) {
  const store = {
      "hood-config": JSON.stringify(config || {}),
      "hood-cache": JSON.stringify(cache || null),
    },
    events = {},
    messages = [],
    requests = [];
  function XHR() {
    requests.push(this);
    this.open = (method, url) => {
      this.url = url;
    };
    this.setRequestHeader = () => {};
    this.send = () => {};
  }
  const pebble = {
    addEventListener: (n, fn) => (events[n] = fn),
    sendAppMessage: (m, ok) => {
      messages.push(m);
      ok();
    },
    openURL: (url) => {
      pebble.url = url;
    },
  };
  vm.runInNewContext(fs.readFileSync("src/pkjs/index.js", "utf8"), {
    require: (n) =>
      n === "./settings"
        ? { demo: false, backend: "https://example.test" }
        : n === "./wire"
          ? wire
          : demo,
    localStorage: {
      getItem: (k) => store[k],
      setItem: (k, v) => (store[k] = v),
      removeItem: (k) => delete store[k],
    },
    Pebble: pebble,
    XMLHttpRequest: XHR,
    Date,
    Math,
    JSON,
    setTimeout: (fn) => fn(),
  });
  return { events, messages, requests, store, pebble };
}
test("first launch requests setup, never silently renders demo", () => {
  const h = harness();
  h.events.ready();
  assert.equal(h.messages.at(-1).ERROR, "SETUP");
  assert.equal(h.requests.length, 0);
});
test("network failure preserves old observation time and labels stale", () => {
  const old = Math.floor(Date.now() / 1000) - 600,
    s = demo.snapshot("demo-main", 0, old);
  s.provider = "robinhood";
  const h = harness(
    { token: "x".repeat(40), source: "robinhood", account: "demo-main" },
    { key: "robinhood:demo-main:0", saved: old, data: s }
  );
  h.events.ready();
  h.requests[0].onerror();
  assert.equal(h.messages[0].UPDATED, old);
  assert.equal(h.messages[0].ERROR, "NO_INTERNET");
  assert.equal(h.messages[0].DEMO, 0);
});
test("expired authorization clears cached data before reporting reconnect", () => {
  const h = harness({ token: "x".repeat(40), source: "robinhood" });
  h.events.ready();
  Object.assign(h.requests[0], {
    status: 401,
    responseText: '{"state":"AUTH_EXPIRED"}',
  });
  h.requests[0].onload();
  assert.equal(h.messages[0].TYPE, 5);
  assert.equal(h.messages[1].ERROR, "AUTH_EXPIRED");
  assert.equal(h.store["hood-cache"], undefined);
});
test("late response after disconnect cannot resurrect financial data", () => {
  const h = harness({ token: "x".repeat(40), source: "robinhood" });
  h.events.ready();
  h.events.showConfiguration();
  const cfg = JSON.parse(decodeURIComponent(h.pebble.url.split("#")[1]));
  h.events.webviewclosed({
    response: encodeURIComponent(
      JSON.stringify({ nonce: cfg.nonce, disconnect: true })
    ),
  });
  const count = h.messages.length;
  Object.assign(h.requests[0], {
    status: 200,
    responseText: JSON.stringify(demo.snapshot("demo-main", 0, 12345)),
  });
  h.requests[0].onload();
  assert.equal(h.messages.length, count);
  assert.equal(h.store["hood-cache"], undefined);
});
test("rapid refreshes serialize HTTP and transfers", () => {
  const h = harness({ token: "x".repeat(40), source: "robinhood" });
  h.events.ready();
  h.events.appmessage({ payload: { PAGE: 1 } });
  h.events.appmessage({ payload: { PAGE: 0 } });
  assert.equal(h.requests.length, 1);
  Object.assign(h.requests[0], {
    status: 200,
    responseText: JSON.stringify(demo.snapshot("demo-main", 0, 12345)),
  });
  h.requests[0].onload();
  assert.equal(h.requests.length, 1); // queued page zero uses fresh phone cache
});

test("malformed success response preserves the last valid cached page", () => {
  const old = Math.floor(Date.now() / 1000) - 600;
  const s = demo.snapshot("demo-main", 0, old);
  s.provider = "robinhood";
  const h = harness(
    { token: "x".repeat(40), source: "robinhood", account: "demo-main" },
    { key: "robinhood:demo-main:0", saved: old, data: s }
  );
  h.events.ready();
  Object.assign(h.requests[0], { status: 200, responseText: '{"version":99}' });
  h.requests[0].onload();
  assert.equal(h.messages[0].UPDATED, old);
  assert.equal(h.messages[0].ERROR, "INVALID_DATA");
  assert.equal(JSON.parse(h.store["hood-cache"]).data.version, 1);
});
