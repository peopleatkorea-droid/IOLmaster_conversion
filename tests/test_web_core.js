const fs = require("fs");
const assert = require("assert");
const core = require("../web/ood-core.js");
const demoExamples = require("../web/demo-examples.js");

const model = JSON.parse(fs.readFileSync("models/biometry_ood_bilateral_v31.json", "utf8"));
const result = core.calculate(model, {
  age: 80,
  al: 23.61,
  meanK: 40.80,
  acd: 1.94,
  lt: 5.58,
  wtw: null,
  cct: null,
});

assert(Math.abs(result.percentile - 92.21205889267232) < 1e-8);
assert(Math.abs(result.distance - 3.544411773204472) < 1e-8);
assert.strictEqual(result.status, "Uncommon anatomy");
assert.strictEqual(result.dominant, "ACD -2.8 SD; LT +2.3 SD");
assert.strictEqual(result.model.model_key, "bilateral_core");
assert.strictEqual(result.profile.length, 4);

const extended = core.calculate(model, {
  age: 80,
  al: 23.61,
  meanK: 40.80,
  acd: 1.94,
  lt: 5.58,
  wtw: 10.99,
  cct: 0.601,
});
assert.strictEqual(extended.model.model_key, "bilateral_extended");
assert(Math.abs(extended.percentile - 95.72502795434605) < 1e-8);
assert.deepStrictEqual(extended.rarity, {
  value: "1 in 23",
  caption: "patient-clustered calibration eyes is this unusual or more",
});
assert(Math.abs(extended.coreSensitivity.percentile - result.percentile) < 1e-10);

assert.strictEqual(core.selectModel(model, { age: 8, wtw: null, cct: null }).model_key, "bilateral_core");
assert.strictEqual(core.selectModel(model, { age: 25, wtw: 12, cct: 0.54 }).model_key, "bilateral_extended");
assert.strictEqual(core.validate(model, { age: 1.5, al: 23.61, meanK: 40.8, acd: 1.94, lt: 5.58, wtw: null, cct: null }), "Age must be between 2 and 100.");

const before18 = core.calculate(model, { age: 17.99, al: 23.05, meanK: 43.31, acd: 3.55, lt: 3.47, wtw: null, cct: null });
const after18 = core.calculate(model, { age: 18.0, al: 23.05, meanK: 43.31, acd: 3.55, lt: 3.47, wtw: null, cct: null });
assert(Math.abs(before18.percentile - after18.percentile) < 1.0);

assert.strictEqual(core.tailExpandedPosition(0), 0);
assert.strictEqual(core.tailExpandedPosition(45), 32.5);
assert.strictEqual(core.tailExpandedPosition(90), 65);
assert.strictEqual(core.tailExpandedPosition(97.5), 87);
assert.strictEqual(core.tailExpandedPosition(100), 100);
assert.strictEqual(core.tailExpandedPosition(-10), 0);
assert.strictEqual(core.tailExpandedPosition(120), 100);

assert.strictEqual(demoExamples.examples.length, 22);
const expectedStudyCases = {
  S038: ["Rare anatomy", 97.621],
  S040: ["Typical anatomy", 4.951],
  P071: ["Typical anatomy", 85.867],
  P111: ["Typical anatomy", 89.932],
  P070: ["Uncommon anatomy", 93.382],
  P091: ["Typical anatomy", 87.271],
  P082: ["Typical anatomy", 79.676],
  D1: ["Uncommon anatomy", 95.725],
  U1: ["Uncommon anatomy", 91.500],
  U2: ["Uncommon anatomy", 93.975],
  U3: ["Uncommon anatomy", 96.499],
  R1: ["Rare anatomy", 97.804],
  R2: ["Rare anatomy", 98.802],
  R3: ["Rare anatomy", 99.639],
  PT: ["Typical anatomy", 50.180],
  PU: ["Uncommon anatomy", 93.255],
  PR: ["Rare anatomy", 97.788],
  YT: ["Typical anatomy", 47.197],
  YU: ["Uncommon anatomy", 93.812],
  YR: ["Rare anatomy", 97.917],
  EA1: ["Uncommon anatomy", 93.330],
  EA2: ["Uncommon anatomy", 91.721],
};
demoExamples.examples.forEach((example) => {
  const exampleResult = core.calculate(model, example);
  const [expectedStatus, expectedPercentile] = expectedStudyCases[example.caseId];
  assert.strictEqual(exampleResult.status, expectedStatus);
  assert(Math.abs(exampleResult.percentile - expectedPercentile) < 0.001);
});
for (const ageGroup of ["Pediatric", "Young adult"]) {
  const ageExamples = demoExamples.examples.filter((example) => example.ageGroup === ageGroup);
  assert.strictEqual(ageExamples.length, 3);
  assert.deepStrictEqual(
    ageExamples.map((example) => example.referenceCategory).sort(),
    ["Rare", "Typical", "Uncommon"],
  );
}
for (let previous = 0; previous < demoExamples.examples.length; previous += 1) {
  [0, 0.2, 0.5, 0.8, 0.999999].forEach((randomValue) => {
    assert.notStrictEqual(demoExamples.chooseIndex(previous, randomValue), previous);
  });
}

console.log("Web OOD core verification OK");
