"use strict";
// Financial formatting uses strings; no floating-point money calculations.
function ascii(s, n) {
  return String(s == null ? "" : s)
    .replace(/[^\x20-\x7e\n]/g, "?")
    .slice(0, n);
}
function amount(v, compact) {
  if (v == null) return "--";
  if (!/^-?\d+(\.\d+)?$/.test(v)) throw Error("Invalid amount");
  var neg = v.charAt(0) === "-",
    p = (neg ? v.slice(1) : v).split("."),
    whole = p[0].replace(/^0+(?=\d)/, ""),
    dec = ((p[1] || "") + "00").slice(0, 2);
  if (compact && whole.length > (typeof compact === "number" ? compact : 6)) {
    var units = ["", "K", "M", "B", "T", "Q", "E"],
      g = Math.floor((whole.length - 1) / 3);
    return (
      (neg ? "-$" : "$") +
      whole.slice(0, whole.length - g * 3) +
      "." +
      whole.slice(whole.length - g * 3, whole.length - g * 3 + 2) +
      units[g]
    );
  }
  return (
    (neg ? "-$" : "$") + whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",") + "." + dec
  );
}
function signed(v) {
  return v == null ? "--" : (v.charAt(0) === "-" ? "" : "+") + v;
}
function signedMoney(v, compact) {
  return v == null
    ? "--"
    : (v.charAt(0) === "-" ? "" : "+") + amount(v, compact);
}
function detail(h, hide) {
  var rows = [
    ascii(h.ticker, 32),
    ascii(h.name, 96),
    "Price  " + amount(h.price),
    "Stock day  " + signedMoney(h.price_day),
    signed(h.price_day_pct) + (h.price_day_pct == null ? "" : "%"),
    "",
    "Shares  " + (hide ? "Hidden" : h.quantity == null ? "--" : h.quantity),
    "Position value",
    hide ? "Hidden" : amount(h.value),
    "Average cost",
    hide ? "Hidden" : amount(h.average_cost),
    "Investment return",
    hide ? "Hidden" : signedMoney(h.unrealized),
    hide
      ? ""
      : signed(h.unrealized_pct) + (h.unrealized_pct == null ? "" : "%"),
    "",
    "Stock day = price move. Investment return = unrealized gain vs cost.",
  ];
  return ascii(rows.join("\n"), 700);
}
function size(message) {
  var n = 1;
  Object.keys(message).forEach(function (k) {
    n +=
      7 +
      (typeof message[k] === "string"
        ? message[k].length + 1
        : Array.isArray(message[k])
          ? message[k].length
          : 4);
  });
  return n;
}
function packets(s, gen, hide) {
  if (
    s.version !== 1 ||
    s.currency !== "USD" ||
    !Array.isArray(s.holdings) ||
    s.holdings.length > 6 ||
    !Number.isFinite(s.as_of)
  )
    throw Error("Invalid snapshot");
  var chart = []; // Backend supplies normalized pixels only for verified history types.
  if (
    !hide &&
    s.history &&
    ["synthetic", "balance_snapshots", "authoritative"].indexOf(
      s.history.kind
    ) >= 0 &&
    Array.isArray(s.history.pixels)
  )
    chart = s.history.pixels.slice(0, 24);
  var messages = [
    {
      TYPE: 1,
      VERSION: 1,
      GEN: gen,
      PAGE: s.page || 0,
      PAGES: s.pages || 1,
      COUNT: s.holdings.length,
      TOTAL_COUNT: s.holdings_count || s.holdings.length,
      UPDATED: s.as_of,
      ACCOUNT: ascii(s.account.name, 31),
      VALUE: hide ? "Hidden" : amount(s.total, true),
      RETURN: hide
        ? "Hidden"
        : s.today
          ? signedMoney(s.today.amount, 4)
          : "Unavailable",
      PERCENT: hide
        ? ""
        : s.today
          ? signed(s.today.percent).length < 17
            ? signed(s.today.percent) + "%"
            : "Too large"
          : "",
      CHART: chart.length ? chart : [255],
      CHART_LABEL: ascii(
        hide
          ? "Balances hidden"
          : s.history
            ? s.history.label
            : "No portfolio history",
        31
      ),
      NOTE: ascii(
        (hide ? "" : "Total USD " + amount(s.total) + "\n") +
          (s.unsupported && s.unsupported.length
            ? "Unsupported: " +
              s.unsupported
                .map(function (u) {
                  return String(u.count) + " " + u.kind;
                })
                .join(", ") +
              ". "
            : "") +
          (s.note || ""),
        127
      ),
      DEMO: s.provider === "demo" ? 1 : 0,
      HIDE: hide ? 1 : 0,
      ERROR: s.state === "OK" ? (s.stale ? "STALE" : "") : ascii(s.state, 31),
    },
  ];
  s.holdings.forEach(function (h, i) {
    messages.push({
      TYPE: 2,
      GEN: gen,
      INDEX: i,
      TICKER: ascii(h.ticker, 23),
      POSITION: hide ? "Hidden" : amount(h.value, true),
      DAILY:
        signed(h.price_day_pct) + (h.price_day_pct == null ? "" : "% price"),
      DETAIL: detail(h, hide),
    });
  });
  messages.push({ TYPE: 3, GEN: gen });
  messages.forEach(function (m) {
    if (size(m) > 1000) throw Error("Message overflow");
  });
  return messages;
}
module.exports = {
  amount: amount,
  signed: signed,
  detail: detail,
  size: size,
  packets: packets,
};
