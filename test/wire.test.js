"use strict";
const test = require("node:test"),
  assert = require("node:assert/strict");
const wire = require("../src/pkjs/wire"),
  demo = require("../src/pkjs/demo");
test("decimal strings preserve cents and signs", () => {
  assert.equal(wire.amount("1234567.89"), "$1,234,567.89");
  assert.equal(wire.amount("-1234567890.12", true), "-$1.23B");
  assert.equal(wire.amount(null), "--");
  assert.equal(wire.amount("0.01"), "$0.01");
  assert.throws(() => wire.amount("NaN"));
});
test("six row chunks are bounded; second page and empty accounts", () => {
  for (const [a, p] of [
    ["demo-main", 0],
    ["demo-main", 1],
    ["demo-empty", 0],
  ]) {
    const s = demo.snapshot(a, p, 12345),
      packets = wire.packets(s, 3, false);
    assert.equal(packets.length, s.holdings.length + 2);
    for (const m of packets) assert.ok(wire.size(m) <= 1000);
    assert.equal(packets[0].DEMO, 1);
    assert.equal(packets.at(-1).TYPE, 3);
  }
});
test("long data and missing values are explicit", () => {
  const s = demo.snapshot("demo-main", 1, 12345);
  s.holdings[0].name = "x".repeat(1000);
  const m = wire.packets(s, 1, false);
  assert.ok(m[1].DETAIL.length <= 700);
  assert.ok(m[2].DETAIL.includes("Price  --"));
  s.holdings.push(...Array(6).fill(s.holdings[0]));
  assert.throws(() => wire.packets(s, 1, false));
});
test("hide balances covers quantity, cost, gains, totals and chart", () => {
  const m = wire.packets(demo.snapshot("demo-main", 0, 12345), 1, true);
  assert.equal(m[0].VALUE, "Hidden");
  assert.deepEqual(m[0].CHART, [255]);
  assert.ok(m[1].DETAIL.includes("Shares  Hidden"));
  assert.ok(!m[1].DETAIL.includes("32.125"));
  assert.ok(m[1].DETAIL.includes("Price  $280.40"));
});
test("unknown history kinds cannot be charted", () => {
  const s = demo.snapshot("demo-main", 0, 12345);
  s.history.kind = "backcast-current-holdings";
  assert.deepEqual(wire.packets(s, 1, false)[0].CHART, [255]);
});

test("large summary numbers fit native fields without truncating amounts", () => {
  const s = demo.snapshot("demo-main", 0, 12345);
  s.total = "9999999.99";
  s.today = { amount: "100000.00", percent: "1000000000000000000.00" };
  const summary = wire.packets(s, 1, false)[0];
  assert.equal(summary.VALUE, "$9.99M");
  assert.equal(summary.RETURN, "+$100.00K");
  assert.equal(summary.PERCENT, "Too large");
  assert.ok(summary.NOTE.includes("$9,999,999.99"));
  assert.ok(summary.NOTE.includes("Unsupported: 1 option"));
});
