import fs from "node:fs";
import assert from "node:assert";
import path from "node:path";
import { fileURLToPath } from "node:url";

await import("../web/ood-core.js");
await import("../web/demo-examples.js");
const core = globalThis.BiometryOODCore;
const demoExamples = globalThis.BiometryOODExamples;
const __dirname = path.dirname(fileURLToPath(import.meta.url));

const modelPath = path.resolve(__dirname, "..", "models", "biometry_ood_bilateral_v32.json");
const model = JSON.parse(fs.readFileSync(modelPath, "utf8"));
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
assert(Math.abs(result.alConditional.percentile - 96.84711041646872) < 1e-8);
assert.strictEqual(result.alConditional.status, "Uncommon geometry given AL");
assert(!result.alConditional.dominant.startsWith("AL "));
assert(result.alConditional.effectiveN > 250);

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
  value: "~1 in 20–30",
  caption: "age-weighted calibration eyes is this unusual or more",
});
assert(Math.abs(extended.coreSensitivity.percentile - result.percentile) < 1e-10);
assert(extended.maxPercentile > 99);
assert.strictEqual(extended.calibrationWarning, "");
assert(extended.alConditional.coreSensitivity);

const fallback = core.calculate(model, {
  age: 80,
  al: 23.61,
  meanK: 40.80,
  acd: 1.94,
  lt: 5.58,
  wtw: 7.5,
  cct: 0.601,
});
assert.strictEqual(fallback.model.tier, "Core");
assert(fallback.modelSelectionWarning.includes("WTW is outside 8–16"));
assert(fallback.modelSelectionWarning.includes("Valid CCT input was ignored"));

const sparseYoung = core.calculate(model, {
  age: 25,
  al: 25.68,
  meanK: 43.30,
  acd: 3.68,
  lt: 3.52,
  wtw: 12,
  cct: 0.54,
});
assert(sparseYoung.maxPercentile < 97.5);
assert(sparseYoung.effectiveN < 50);
assert(sparseYoung.calibrationWarning.includes("Rare threshold is not attainable"));

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

assert.strictEqual(demoExamples.examples.length, 12);
const expectedSyntheticCases = {
  "SYN-A-T1": ["Typical anatomy", 0.748],
  "SYN-A-T2": ["Typical anatomy", 0.251],
  "SYN-A-U1": ["Uncommon anatomy", 94.998],
  "SYN-A-U2": ["Uncommon anatomy", 92.038],
  "SYN-A-R1": ["Rare anatomy", 98.801],
  "SYN-A-R2": ["Rare anatomy", 99.627],
  "SYN-P-T": ["Typical anatomy", 5.555],
  "SYN-P-U": ["Uncommon anatomy", 91.042],
  "SYN-P-R": ["Rare anatomy", 97.736],
  "SYN-Y-T": ["Typical anatomy", 3.995],
  "SYN-Y-U": ["Uncommon anatomy", 93.663],
  "SYN-Y-R": ["Uncommon anatomy", 97.268],
};
demoExamples.examples.forEach((example) => {
  const exampleResult = core.calculate(model, example);
  const [expectedStatus, expectedPercentile] = expectedSyntheticCases[example.caseId];
  assert.strictEqual(exampleResult.status, expectedStatus);
  assert(Math.abs(exampleResult.percentile - expectedPercentile) < 0.001);
  assert.strictEqual(example.exampleType, "Synthetic educational example");
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
