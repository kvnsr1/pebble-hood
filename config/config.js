(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var initial = {}, returned = "", restoreKey = "hood-config-return";
  try {
    if (location.hash.indexOf("#robinhood=") === 0) {
      returned = location.hash.slice(11);
      initial = JSON.parse(sessionStorage.getItem(restoreKey) || "{}");
    } else {
      initial = JSON.parse(decodeURIComponent(location.hash.slice(1)));
    }
  } catch (_) { initial = {}; }
  if (!initial || typeof initial !== "object" || Array.isArray(initial)) initial = {};
  try { sessionStorage.removeItem(restoreKey); } catch (_) {}
  history.replaceState(null, "", location.pathname);
  var token = initial.token || "", nonce = initial.nonce || "", csrf = "";
  var accountRequest = 0;
  var messages = {
    AUTH_REQUIRED: "Robinhood is not connected. Demo is available.",
    AUTH_EXPIRED: "Robinhood authorization expired. Reconnect to continue.",
    SCHEMA_UNVERIFIED: "Robinhood authorization is saved. Live data still needs a one-time verification; Demo is available.",
    CONNECTED: "Robinhood authorization is saved. Choose Robinhood to check account access.",
    AUTH_CANCELED: "Robinhood sign-in was canceled. Your previous connection is unchanged.",
    OAUTH_EXPIRED: "Sign-in expired. Start again.",
    OAUTH_STATE_INVALID: "This sign-in cannot be verified. Start again from settings.",
    OAUTH_SESSION_LOST: "The sign-in browser session was lost. Reopen settings and enter a fresh setup code.",
    OAUTH_ISSUER_INVALID: "The sign-in response could not be verified. Start again.",
    OAUTH_CODE_MISSING: "Robinhood did not return an authorization code. Start again.",
    OAUTH_PROVIDER_FAILURE: "Could not reach Robinhood. Try again later.",
    TOKEN_EXCHANGE_FAILED: "Robinhood did not complete authorization. Start again.",
    REGISTRATION_FAILED: "Robinhood did not accept this connection setup.",
    OAUTH_METADATA_CHANGED: "Robinhood changed its authorization interface. Connection needs review.",
    BROWSER_AUTH_REQUIRED: "Enter a fresh setup code to unlock connection controls.",
    HTTPS_BACKEND_REQUIRED: "The private backend needs a configured HTTPS address.",
    PAIRING_EXPIRED: "The setup code expired or was already used. Get a new code.",
    RATE_LIMITED: "Please wait a minute before trying again.",
  };
  function message(s) { return messages[s] || s; }
  function status(s) { $("status").textContent = message(s); }
  $("source").value = initial.source || "demo";
  $("hide").checked = !!initial.hide;
  function api(path, body) {
    return fetch(path, {
      method: body ? "POST" : "GET",
      headers: { "Content-Type": "application/json", Authorization: "Bearer " + token },
      body: body ? JSON.stringify(body) : undefined,
      credentials: "same-origin",
    }).then(function (r) {
      return r.json().then(function (d) {
        if (!r.ok) throw Error(d.state || d.detail || "Connection failed");
        return d;
      });
    });
  }
  function accounts() {
    var request = ++accountRequest;
    $("account").innerHTML = "";
    $("save").disabled = true;
    api("/v1/accounts?source=" + $("source").value).then(function (d) {
      if (request !== accountRequest) return;
      d.accounts.forEach(function (a) {
        var o = document.createElement("option");
        o.value = a.id;
        o.textContent = a.name;
        $("account").appendChild(o);
      });
      if (initial.account) $("account").value = initial.account;
      if (!$("account").value && $("account").options.length) $("account").selectedIndex = 0;
      $("save").disabled = !$("account").value || !nonce;
      status(nonce ? "Choose an account, then save to watch." : "Open these settings from the Pebble app to save to your watch.");
    }).catch(function (e) { if (request === accountRequest) status(e.message); });
  }
  function connection() {
    $("connect").disabled = true;
    $("disconnect-broker").disabled = true;
    return api("/v1/connection").then(function (d) {
      csrf = d.csrf || "";
      $("connection-status").textContent = message(d.state);
      $("connect").textContent = d.state === "AUTH_REQUIRED" ? "Connect Robinhood" : "Reconnect Robinhood";
      $("connect").disabled = !csrf || !d.https_configured;
      $("disconnect-broker").disabled = !csrf || d.state === "AUTH_REQUIRED";
      $("authorize").hidden = !!csrf;
    }).catch(function (e) {
      $("connection-status").textContent = message(e.message);
    });
  }
  function ready() {
    $("pairing").hidden = true;
    $("settings").hidden = false;
    accounts();
    connection();
    if (returned && returned !== "CONNECTED") {
      $("login-result").hidden = false;
      $("login-result").textContent = message(returned);
    }
  }
  $("pair").onclick = function () {
    $("pair").disabled = true;
    api("/v1/pair", { code: $("code").value }).then(function (d) {
      token = d.token;
      $("code").value = "";
      ready();
    }).catch(function (e) { status(e.message); }).then(function () { $("pair").disabled = false; });
  };
  $("authorize").onclick = function () { $("pairing").hidden = false; $("code").focus(); };
  $("connect").onclick = function () {
    $("login-result").hidden = true;
    $("connect").disabled = true;
    status("Opening Robinhood sign-in…");
    api("/v1/connection/start", { csrf: csrf }).then(function (d) {
      // Preserve Pebble's return nonce through a same-webview OAuth round trip.
      // Storage is session-only and cleared immediately when settings returns.
      sessionStorage.setItem(restoreKey, JSON.stringify({
        token: token, nonce: nonce, source: $("source").value,
        account: $("account").value, hide: $("hide").checked,
      }));
      if (d.url.indexOf("https://robinhood.com/oauth?") !== 0) throw Error("Invalid sign-in address");
      location.href = d.url;
    }).catch(function (e) { status(e.message); connection(); });
  };
  $("source").onchange = accounts;
  function close(payload) {
    location.href = "pebblejs://close#" + encodeURIComponent(JSON.stringify(payload));
  }
  $("save").onclick = function () {
    close({ nonce: nonce, token: token, source: $("source").value,
      account: $("account").value, hide: $("hide").checked });
  };
  function disconnect(path, body) {
    $("disconnect").disabled = true;
    $("disconnect-broker").disabled = true;
    api(path, body).then(function () {
      token = "";
      try { sessionStorage.removeItem(restoreKey); } catch (_) {}
      close({ nonce: nonce, disconnect: true });
    }).catch(function (e) { status(e.message); $("disconnect").disabled = false; connection(); });
  }
  $("disconnect").onclick = function () { disconnect("/v1/disconnect", {}); };
  $("disconnect-broker").onclick = function () { disconnect("/v1/connection/disconnect", { csrf: csrf }); };
  if (token) ready();
  else if (returned) status("The Pebble settings session was lost. Reopen settings from the Pebble app and enter a fresh setup code.");
})();
