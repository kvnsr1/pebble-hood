"use strict";
var settings = require("./settings"),
  wire = require("./wire"),
  demo = require("./demo");
var config,
  cache,
  gen = 0,
  busy = false,
  pending = null,
  nonce = "",
  page = 0,
  era = 0;
try {
  config = JSON.parse(localStorage.getItem("hood-config") || "{}");
  cache = JSON.parse(localStorage.getItem("hood-cache") || "null");
} catch (_) {
  config = {};
  cache = null;
}
var account = config.account || "demo-main";
function sendAll(list, done) {
  var i = 0,
    tries = 0,
    sendEra = era;
  function next() {
    if (sendEra !== era) return;
    if (i === list.length) {
      done();
      return;
    }
    Pebble.sendAppMessage(
      list[i],
      function () {
        i++;
        tries = 0;
        next();
      },
      function () {
        if (++tries < 3) setTimeout(next, 350 * tries);
        else done();
      }
    );
  }
  next();
}
function error(code) {
  sendAll([{ TYPE: 4, ERROR: code }], function () {});
}
function api(path, done) {
  var requestEra = era;
  var x = new XMLHttpRequest();
  x.open("GET", settings.backend + path, true);
  x.timeout = 15000;
  x.setRequestHeader("Authorization", "Bearer " + config.token);
  x.onload = function () {
    if (requestEra !== era) return;
    var d;
    try {
      d = JSON.parse(x.responseText);
    } catch (_) {
      done("PROVIDER_FAILURE");
      return;
    }
    if (x.status !== 200) {
      done(
        d.state ||
          d.detail ||
          (x.status === 401 ? "AUTH_EXPIRED" : "PROVIDER_FAILURE")
      );
      return;
    }
    done(null, d);
  };
  x.onerror = function () {
    if (requestEra !== era) return;
    done("NO_INTERNET");
  };
  x.ontimeout = function () {
    if (requestEra !== era) return;
    done("NO_INTERNET");
  };
  x.send();
}
function remember() {
  localStorage.setItem("hood-config", JSON.stringify(config));
}
function render(s, code, done) {
  if (code) {
    s = JSON.parse(JSON.stringify(s));
    s.stale = true;
    s.state = code;
  }
  try {
    sendAll(wire.packets(s, ++gen, !!config.hide), done);
  } catch (_) {
    error("INVALID_DATA");
    done();
  }
}
function refresh(requestedPage) {
  if (busy) {
    pending = requestedPage;
    return;
  }
  busy = true;
  page = requestedPage;
  var refreshEra = era;
  function finish() {
    if (refreshEra !== era) return;
    busy = false;
    if (pending !== null) {
      var p = pending;
      pending = null;
      refresh(p);
    }
  }
  var now = Math.floor(Date.now() / 1000);
  if (settings.demo) {
    render(demo.snapshot(account, page, now), null, finish);
    return;
  }
  if (!settings.backend || !config.token) {
    error("SETUP");
    finish();
    return;
  }
  var key = (config.source || "robinhood") + ":" + account + ":" + page;
  if (
    cache &&
    cache.key === key &&
    now >= cache.saved &&
    now - cache.saved < 60
  ) {
    render(cache.data, null, finish);
    return;
  }
  api(
    "/v1/portfolio?source=" +
      encodeURIComponent(config.source || "robinhood") +
      "&account=" +
      encodeURIComponent(account) +
      "&page=" +
      page,
    function (err, s) {
      if (err) {
        if (err === "AUTH_EXPIRED" || err === "AUTH_REQUIRED") {
          cache = null;
          localStorage.removeItem("hood-cache");
          sendAll([{ TYPE: 5 }], function () {
            error(err);
            finish();
          });
          return;
        }
        if (cache && cache.key === key) render(cache.data, err, finish);
        else {
          error(err);
          finish();
        }
        return;
      }
      try {
        wire.packets(s, gen + 1, !!config.hide);
      } catch (_) {
        if (cache && cache.key === key)
          render(cache.data, "INVALID_DATA", finish);
        else {
          error("INVALID_DATA");
          finish();
        }
        return;
      }
      cache = { key: key, saved: now, data: s };
      localStorage.setItem("hood-cache", JSON.stringify(cache));
      render(s, null, finish);
    }
  );
}
Pebble.addEventListener("ready", function () {
  refresh(0);
});
Pebble.addEventListener("appmessage", function (e) {
  var p = e.payload,
    cmd = p.CMD || 0;
  if (cmd === 1) {
    if (settings.demo) {
      account = account === "demo-main" ? "demo-empty" : "demo-main";
      config.account = account;
      remember();
      refresh(0);
    } else
      api(
        "/v1/accounts?source=" +
          encodeURIComponent(config.source || "robinhood"),
        function (err, d) {
          if (err) {
            error(err);
            return;
          }
          if (!d.accounts.length) {
            error("EMPTY_ACCOUNTS");
            return;
          }
          var i = 0;
          d.accounts.forEach(function (a, n) {
            if (a.id === account) i = (n + 1) % d.accounts.length;
          });
          account = d.accounts[i].id;
          config.account = account;
          remember();
          refresh(0);
        }
      );
  } else if (cmd === 2) {
    config.hide = !config.hide;
    remember();
    refresh(page);
  } else refresh(p.PAGE || 0);
});
Pebble.addEventListener("showConfiguration", function () {
  if (!settings.backend) {
    error("DEMO_SETTINGS");
    return;
  }
  nonce = String(Date.now()) + ":" + String(Math.random()).slice(2);
  Pebble.openURL(
    settings.backend +
      "/configure#" +
      encodeURIComponent(
        JSON.stringify({
          nonce: nonce,
          token: config.token || "",
          source: config.source || "demo",
          account: account,
          hide: !!config.hide,
        })
      )
  );
});
Pebble.addEventListener("webviewclosed", function (e) {
  if (!e.response) return;
  try {
    var c = JSON.parse(decodeURIComponent(e.response));
    if (!nonce || c.nonce !== nonce) throw Error("Bad config");
    nonce = "";
    if (c.disconnect) {
      era++;
      busy = false;
      pending = null;
      config = {};
      cache = null;
      localStorage.removeItem("hood-cache");
      remember();
      sendAll([{ TYPE: 5 }], function () {
        error("SETUP");
      });
      return;
    }
    if (
      ["demo", "robinhood"].indexOf(c.source) < 0 ||
      typeof c.token !== "string" ||
      c.token.length < 32 ||
      c.token.length > 100 ||
      typeof c.account !== "string" ||
      c.account.length > 96
    )
      throw Error("Bad config");
    era++;
    busy = false;
    pending = null;
    config = {
      token: c.token,
      source: c.source,
      account: c.account,
      hide: !!c.hide,
    };
    account = c.account;
    cache = null;
    localStorage.removeItem("hood-cache");
    remember();
    sendAll([{ TYPE: 5 }], function () {
      refresh(0);
    });
  } catch (_) {
    error("CONFIG_INVALID");
  }
});
