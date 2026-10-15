(function () {
  "use strict";
  var $ = function (id) {
    return document.getElementById(id);
  };
  var initial;
  try {
    initial = JSON.parse(decodeURIComponent(location.hash.slice(1)));
  } catch (_) {
    initial = {};
  }
  history.replaceState(null, "", location.pathname);
  var token = initial.token || "",
    nonce = initial.nonce || "";
  $("source").value = initial.source || "demo";
  $("hide").checked = !!initial.hide;
  function status(s) {
    $("status").textContent = s;
  }
  function api(path, body) {
    return fetch(path, {
      method: body ? "POST" : "GET",
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer " + token,
      },
      body: body ? JSON.stringify(body) : undefined,
      credentials: "omit",
    }).then(function (r) {
      return r.json().then(function (d) {
        if (!r.ok) throw Error(d.state || d.detail || "Connection failed");
        return d;
      });
    });
  }
  function accounts() {
    $("account").innerHTML = "";
    $("save").disabled = true;
    api("/v1/accounts?source=" + $("source").value)
      .then(function (d) {
        d.accounts.forEach(function (a) {
          var o = document.createElement("option");
          o.value = a.id;
          o.textContent = a.name;
          $("account").appendChild(o);
        });
        if (initial.account) $("account").value = initial.account;
        if (!$("account").value && $("account").options.length)
          $("account").selectedIndex = 0;
        $("save").disabled = !$("account").value;
        status("Connected to backend.");
      })
      .catch(function (e) {
        status(
          e.message === "SCHEMA_UNVERIFIED"
            ? "Robinhood response fields still need verification. Choose Demo for now."
            : e.message
        );
      });
  }
  function ready() {
    $("pairing").hidden = true;
    $("settings").hidden = false;
    accounts();
  }
  $("pair").onclick = function () {
    api("/v1/pair", { code: $("code").value })
      .then(function (d) {
        token = d.token;
        $("code").value = "";
        ready();
      })
      .catch(function (e) {
        status(e.message);
      });
  };
  $("source").onchange = accounts;
  $("save").onclick = function () {
    location.href =
      "pebblejs://close#" +
      encodeURIComponent(
        JSON.stringify({
          nonce: nonce,
          token: token,
          source: $("source").value,
          account: $("account").value,
          hide: $("hide").checked,
        })
      );
  };
  $("disconnect").onclick = function () {
    api("/v1/disconnect", {})
      .then(function () {
        token = "";
        location.href =
          "pebblejs://close#" +
          encodeURIComponent(
            JSON.stringify({ nonce: nonce, disconnect: true })
          );
      })
      .catch(function (e) {
        status(e.message);
      });
  };
  if (token) ready();
})();
