const fs = require("fs");
const assert = require("assert");
const core = require("../web/ood-core.js");

const model = JSON.parse(fs.readFileSync("models/biometry_ood_age_stratified_v2.json", "utf8"));
const result = core.calculate(model, {
  age: 80,
  al: 23.61,
  meanK: 40.80,
  acd: 1.94,
  lt: 5.58,
  wtw: null,
  cct: null,
});

assert(Math.abs(result.percentile - 93.57184409540431) < 1e-10);
assert(Math.abs(result.distance - 3.318076665704779) < 1e-10);
assert.strictEqual(result.score, 1);
assert.strictEqual(result.status, "Uncommon anatomy");
assert.strictEqual(result.dominant, "ACD vs age -2.6 SD; LT vs age +2.2 SD");
assert.strictEqual(result.model.model_key, "adult_core");

const extended = core.calculate(model, {
  age: 80,
  al: 23.61,
  meanK: 40.80,
  acd: 1.94,
  lt: 5.58,
  wtw: 10.99,
  cct: 0.601,
});
assert.strictEqual(extended.model.model_key, "adult_extended");
assert(Math.abs(extended.percentile - 96.39220250218213) < 1e-10);

assert.strictEqual(core.selectModel(model, { age: 8, wtw: null, cct: null }).model_key, "pediatric_core");
assert.strictEqual(core.selectModel(model, { age: 25, wtw: 12, cct: 0.54 }).model_key, "young_adult_extended");
assert.strictEqual(core.validate(model, { age: 1.5, al: 23.61, meanK: 40.8, acd: 1.94, lt: 5.58, wtw: null, cct: null }), "Age must be between 2 and 100.");

console.log("Web OOD core verification OK");
