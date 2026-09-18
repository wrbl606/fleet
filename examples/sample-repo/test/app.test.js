const test = require("node:test");
const assert = require("node:assert");
const { add } = require("../src/app.js");

test("add returns the sum", () => {
  assert.strictEqual(add(2, 3), 5);
});

test("add handles negatives", () => {
  assert.strictEqual(add(-2, 1), -1);
});
