// Settings navigation tests. No brokerage requests; all responses are synthetic.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const script = fs.readFileSync("config/config.js", "utf8");
const csrf = "synthetic-csrf-" + "x".repeat(32);
const initial = { token: "synthetic-view-token", nonce: "pebble-return-nonce", source: "demo", account: "demo-main", hide: true };
function response(d, ok = true) { return { ok, json: () => Promise.resolve(d) }; }
async function settle() { for (let i = 0; i < 15; i++) await Promise.resolve(); }
function boot(options = {}) {
  const elements = {}, calls = [], storage = new Map(options.storage || []);
  const location = { pathname: "/configure", hash: options.hash === undefined ? "#" + encodeURIComponent(JSON.stringify(initial)) : options.hash, href: "" };
  function element(id) {
    if (elements[id]) return elements[id];
    const e = { value: "", checked: false, hidden: false, disabled: false, textContent: "", options: [], focus() {}, appendChild(o) { this.options.push(o); if (!this.value) this.value = o.value; } };
    Object.defineProperty(e, "innerHTML", { set() { e.options = []; e.value = ""; } });
    Object.defineProperty(e, "selectedIndex", { set(i) { e.value = e.options[i].value; } });
    elements[id] = e;
    return e;
  }
  const api = options.api || ((path) => {
    if (path === "/v1/connection") return response({ state: "AUTH_REQUIRED", csrf, browser_authorized: true, https_configured: true });
    if (path.indexOf("/v1/accounts") === 0) return response({ accounts: [{ id: "demo-main", name: "Demo" }] });
    if (path === "/v1/connection/start") return response({ url: "https://robinhood.com/oauth?state=synthetic" });
    if (path === "/v1/pair") return response({ token: "new-synthetic-token" });
    return response({ disconnected: true });
  });
  for (const match of fs.readFileSync("config/index.html", "utf8").matchAll(/id="([^"]+)"/g)) element(match[1]);
  vm.runInNewContext(script, {
    document: { getElementById: element, createElement: () => ({}) }, location,
    history: { replaceState() { location.hash = ""; } },
    sessionStorage: { getItem: k => storage.get(k) || null, setItem: (k, v) => storage.set(k, v), removeItem: k => storage.delete(k) },
    fetch(path, args) { calls.push({ path, args }); return Promise.resolve(api(path, args)); },
  });
  return { elements, calls, storage, location };
}

test("settings pairs, preserves browser cookies and saves only phone configuration", async () => {
  const b = boot({ hash: "" });
  b.elements.code.value = "one-use-synthetic-code";
  b.elements.pair.onclick();
  await settle();
  assert.equal(b.elements.pairing.hidden, true);
  assert.equal(b.elements.connect.disabled, false);
  assert.equal(b.elements.save.disabled, true); // No Pebble nonce when opened standalone.
  assert.ok(b.calls.every(c => c.args.credentials === "same-origin"));
});

test("connect preserves Pebble return context through official browser navigation", async () => {
  const b = boot();
  await settle();
  b.elements.connect.onclick();
  await settle();
  assert.equal(b.location.href, "https://robinhood.com/oauth?state=synthetic");
  const saved = b.storage.get("hood-config-return");
  assert.equal(JSON.parse(saved).nonce, initial.nonce);
  const call = b.calls.find(c => c.path === "/v1/connection/start");
  assert.equal(JSON.parse(call.args.body).csrf, csrf);
  const back = boot({ hash: "#robinhood=CONNECTED", storage: [["hood-config-return", saved]] });
  await settle();
  assert.equal(back.storage.has("hood-config-return"), false);
  back.elements.save.onclick();
  const closed = JSON.parse(decodeURIComponent(back.location.href.split("#")[1]));
  assert.equal(closed.nonce, initial.nonce);
  assert.equal(closed.hide, true);
  assert.equal(closed.token, initial.token);
  assert.equal(Object.hasOwn(closed, "csrf"), false);
});

test("view token without browser setup cannot enable connection controls", async () => {
  const b = boot({ api: path => path === "/v1/connection" ? response({ state: "SCHEMA_UNVERIFIED", csrf: null, https_configured: true }) : response({ accounts: [] }) });
  await settle();
  assert.equal(b.elements.connect.disabled, true);
  assert.equal(b.elements["disconnect-broker"].disabled, true);
  assert.equal(b.elements.authorize.hidden, false);
  assert.match(b.elements["connection-status"].textContent, /one-time verification/);
});

test("canceled OAuth remains visible after account loading", async () => {
  const b = boot({ hash: "#robinhood=AUTH_CANCELED", storage: [["hood-config-return", JSON.stringify(initial)]] });
  await settle();
  assert.equal(b.elements["login-result"].hidden, false);
  assert.match(b.elements["login-result"].textContent, /canceled/);
});

test("late account response cannot restore another selected source", async () => {
  let resolveDemo, resolveLive;
  const b = boot({ api: path => {
    if (path === "/v1/connection") return response({ state: "CONNECTED", csrf, https_configured: true });
    if (path.endsWith("source=demo")) return new Promise(r => { resolveDemo = r; });
    return new Promise(r => { resolveLive = r; });
  } });
  b.elements.source.value = "robinhood";
  b.elements.source.onchange();
  resolveLive(response({ accounts: [{ id: "real-shaped-synthetic", name: "Synthetic live account" }] }));
  await settle();
  resolveDemo(response({ accounts: [{ id: "demo-main", name: "Demo" }] }));
  await settle();
  assert.equal(b.elements.account.options.length, 1);
  assert.equal(b.elements.account.options[0].value, "real-shaped-synthetic");
});

test("broker disconnect uses browser CSRF and returns a clear instruction to Pebble", async () => {
  const b = boot();
  await settle();
  b.elements["disconnect-broker"].onclick();
  await settle();
  const call = b.calls.find(c => c.path === "/v1/connection/disconnect");
  assert.equal(JSON.parse(call.args.body).csrf, csrf);
  const closed = JSON.parse(decodeURIComponent(b.location.href.split("#")[1]));
  assert.deepEqual(closed, { nonce: initial.nonce, disconnect: true });
});
