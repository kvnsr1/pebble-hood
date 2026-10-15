"use strict";
var fixture = require("./demo.json");
function snapshot(account, page, now) {
  var s = JSON.parse(JSON.stringify(fixture)),
    empty = account === "demo-empty";
  s.as_of = now;
  s.page = page || 0;
  s.pages = empty ? 1 : 2;
  s.holdings_count = empty ? 0 : s.holdings.length;
  s.account = empty ? { id: "demo-empty", name: "Demo empty" } : s.account;
  s.total = empty ? "0.00" : s.total;
  s.today = empty ? null : s.today;
  s.holdings = empty ? [] : s.holdings.slice(s.page * 6, s.page * 6 + 6);
  s.history.pixels = empty
    ? []
    : [0, 37, 25, 43, 4, 64, 74, 66, 91, 77, 88, 100];
  s.note = empty
    ? "No holdings in this demo account."
    : "Includes cash + 1 option. Options unsupported. Synthetic data.";
  return s;
}
module.exports = { snapshot: snapshot };
