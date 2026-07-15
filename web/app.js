const MODEL_URL = "../models/biometry_ood_bilateral_v32.json";

const form = document.querySelector("#calculator-form");
const calculateButton = document.querySelector("#calculate-button");
const exampleButton = document.querySelector("#example-button");
const resetButton = document.querySelector("#reset-button");
const validationMessage = document.querySelector("#validation-message");
const exampleCaption = document.querySelector("#example-caption");
const modelPreview = document.querySelector("#model-preview");
const modelState = document.querySelector("#model-state");
const resultEmpty = document.querySelector("#result-empty");
const resultContent = document.querySelector("#result-content");

let modelBundle = null;
let previousExampleIndex = null;

function readInputs() {
  return {
    age: Number(document.querySelector("#age").value),
    al: Number(document.querySelector("#al").value),
    meanK: Number(document.querySelector("#mean-k").value),
    acd: Number(document.querySelector("#acd").value),
    lt: Number(document.querySelector("#lt").value),
    wtw: document.querySelector("#wtw").value === "" ? null : Number(document.querySelector("#wtw").value),
    cct: document.querySelector("#cct").value === "" ? null : Number(document.querySelector("#cct").value),
  };
}

function formatPercentile(value) {
  if (value > 0 && value < 0.1) return "<0.1";
  if (value > 99.9) return ">99.9";
  return value.toFixed(1);
}

function profilePosition(value, minimum, maximum) {
  if (maximum <= minimum) return 50;
  return Math.min(100, Math.max(0, (100 * (value - minimum)) / (maximum - minimum)));
}

function renderProfile(profile) {
  const container = document.querySelector("#profile-list");
  container.replaceChildren();
  profile.forEach((item) => {
    const span = Math.max(0.5, item.q97_5 - item.q2_5);
    const minimum = Math.min(item.q2_5 - 0.12 * span, item.standardizedValue - 0.08 * span);
    const maximum = Math.max(item.q97_5 + 0.12 * span, item.standardizedValue + 0.08 * span);

    const row = document.createElement("div");
    row.className = "profile-row";

    const name = document.createElement("span");
    name.className = "profile-name";
    name.textContent = item.label;

    const track = document.createElement("div");
    track.className = "profile-track";
    track.setAttribute("aria-label", `${item.label} reference distribution`);
    const range95 = document.createElement("span");
    range95.className = "profile-range95";
    range95.style.left = `${profilePosition(item.q2_5, minimum, maximum)}%`;
    range95.style.width = `${profilePosition(item.q97_5, minimum, maximum) - profilePosition(item.q2_5, minimum, maximum)}%`;
    const range50 = document.createElement("span");
    range50.className = "profile-range50";
    range50.style.left = `${profilePosition(item.q25, minimum, maximum)}%`;
    range50.style.width = `${profilePosition(item.q75, minimum, maximum) - profilePosition(item.q25, minimum, maximum)}%`;
    const median = document.createElement("span");
    median.className = "profile-median";
    median.style.left = `${profilePosition(item.q50, minimum, maximum)}%`;
    const marker = document.createElement("span");
    marker.className = "profile-marker";
    marker.style.left = `${profilePosition(item.standardizedValue, minimum, maximum)}%`;
    track.append(range95, range50, median, marker);

    const value = document.createElement("span");
    value.className = "profile-value";
    const decimals = item.name === "CCT" ? 3 : 2;
    const observed = document.createElement("strong");
    observed.textContent = `${item.observed.toFixed(decimals)} ${item.unit}`;
    value.append(observed, ` · P${formatPercentile(item.marginalPercentile)}`);

    row.append(name, track, value);
    container.append(row);
  });
}

function showResult(result) {
  document.querySelector("#percentile-value").textContent = result.percentile.toFixed(1);
  document.querySelector("#distance-value").textContent = result.distance.toFixed(3);
  document.querySelector("#meaning-value").textContent = result.status;
  document.querySelector("#meaning-value").className = `meaning-value ${result.statusClass}`;
  document.querySelector("#rarity-value").textContent = result.rarity.value;
  document.querySelector("#rarity-caption").textContent = result.rarity.caption;
  document.querySelector("#expected-acd").textContent = `${result.expectedAcd.toFixed(3)} mm`;
  document.querySelector("#adjusted-acd").textContent = `${result.adjustedAcd >= 0 ? "+" : ""}${result.adjustedAcd.toFixed(3)} mm`;
  document.querySelector("#expected-lt").textContent = `${result.expectedLt.toFixed(3)} mm`;
  document.querySelector("#adjusted-lt").textContent = `${result.adjustedLt >= 0 ? "+" : ""}${result.adjustedLt.toFixed(3)} mm`;
  document.querySelector("#dominant-deviation").textContent = result.dominant;
  document.querySelector("#conditional-percentile").textContent = result.alConditional.percentile.toFixed(1);
  document.querySelector("#conditional-status").textContent = result.alConditional.status;
  document.querySelector("#conditional-status").className = result.alConditional.statusClass;
  document.querySelector("#conditional-context").textContent = `${result.alConditional.rarity.value} · ${result.alConditional.rarity.caption}`;
  document.querySelector("#conditional-deviation").textContent = result.alConditional.dominant;
  document.querySelector("#conditional-distance").textContent = result.alConditional.distance.toFixed(3);
  document.querySelector("#conditional-calibration").textContent = `Age+AL-local · effective N ${result.alConditional.effectiveN.toFixed(0)} · ceiling ${result.alConditional.maxPercentile.toFixed(1)}th`;
  document.querySelector("#selected-model-detail").textContent = `${result.model.stratum_label} / ${result.model.tier}`;
  document.querySelector("#result-model-chip").textContent = `${result.model.stratum_label} · ${result.model.tier}`;
  document.querySelector("#result-model-chip").hidden = false;
  document.querySelector("#core-sensitivity").textContent = result.coreSensitivity
    ? `${result.coreSensitivity.percentile.toFixed(1)}th · ${result.coreSensitivity.status} (${result.coreSensitivity.difference >= 0 ? "+" : ""}${result.coreSensitivity.difference.toFixed(1)})`
    : "Core model selected";
  document.querySelector("#calibration-detail").textContent = `Age-local · effective N ${result.effectiveN.toFixed(0)} · ceiling ${result.maxPercentile.toFixed(1)}th`;
  document.querySelector("#result-model-version").textContent = result.model.model_version;
  document.querySelector("#result-test-cohort").textContent = `${result.model.test_rows.toLocaleString()} eyes / ${result.model.test_patients.toLocaleString()} patients (${result.model.tier})`;
  document.querySelector("#result-limitations").textContent = `Single-center IOLMaster 700 reference, ages ${result.model.display_age_range}; clinical indication not verified by EMR; external and postoperative outcome validation not completed.`;
  const resultWarning = document.querySelector("#result-warning");
  const warnings = [
    result.modelSelectionWarning,
    result.calibrationWarning,
    result.alConditional.calibrationWarning,
  ].filter(Boolean);
  resultWarning.textContent = warnings.join(" ");
  resultWarning.hidden = warnings.length === 0;
  document.querySelector("#model-version").textContent = result.model.model_version;
  document.querySelector("#reference-patients").textContent = `${result.model.reference_rows.toLocaleString()} / ${result.model.reference_patients.toLocaleString()}`;
  document.querySelector("#derivation-patients").textContent = `${result.model.derivation_rows.toLocaleString()} / ${result.model.derivation_patients.toLocaleString()}`;
  document.querySelector("#age-range").textContent = result.model.display_age_range;
  document.querySelector("#cohort-note").textContent = `${result.model.cohort_status} External and postoperative outcome validation are required before clinical decision-support use.`;
  const marker = document.querySelector("#track-marker");
  const markerPosition = BiometryOODCore.tailExpandedPosition(result.percentile);
  marker.className = `track-marker ${result.statusClass}`;
  marker.style.left = `${markerPosition}%`;
  marker.classList.toggle("marker-edge-left", markerPosition < 5);
  marker.classList.toggle("marker-edge-right", markerPosition > 95);
  document.querySelector("#track-marker-badge").textContent = `${formatPercentile(result.percentile)}%`;
  void marker.offsetWidth;
  marker.classList.add("is-animating");
  renderProfile(result.profile);
  resultEmpty.hidden = true;
  resultContent.hidden = false;
}

function resetResults() {
  resultEmpty.hidden = false;
  resultContent.hidden = true;
  validationMessage.textContent = "";
  document.querySelector("#result-model-chip").hidden = true;
  document.querySelector("#result-warning").hidden = true;
}

function updateModelPreview() {
  if (!modelBundle) return;
  const selected = BiometryOODCore.selectModel(modelBundle, readInputs());
  const values = readInputs();
  const warning = BiometryOODCore.modelSelectionWarning(modelBundle, values);
  modelPreview.textContent = selected
    ? `${selected.stratum_label} / ${selected.tier} model selected${selected.tier === "Core" ? " · add both WTW and CCT for Extended" : ""}`
    : "No reference model is available for this age.";
  const selectionWarning = document.querySelector("#model-selection-warning");
  selectionWarning.textContent = warning;
  selectionWarning.hidden = !warning;
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const values = readInputs();
  const error = BiometryOODCore.validate(modelBundle, values);
  validationMessage.textContent = error;
  if (error) return;
  showResult(BiometryOODCore.calculate(modelBundle, values));
});

form.addEventListener("input", () => {
  exampleCaption.hidden = true;
  document.querySelector("#model-selection-warning").hidden = true;
  updateModelPreview();
});

function loadExample(requestedIndex = null) {
  const exampleIndex = Number.isInteger(requestedIndex)
    && requestedIndex >= 0
    && requestedIndex < BiometryOODExamples.examples.length
    ? requestedIndex
    : BiometryOODExamples.chooseIndex(previousExampleIndex);
  const example = BiometryOODExamples.examples[exampleIndex];
  previousExampleIndex = exampleIndex;

  document.querySelector("#age").value = example.age.toFixed(example.age % 1 === 0 ? 0 : 1);
  document.querySelector("#al").value = example.al.toFixed(3);
  document.querySelector("#mean-k").value = example.meanK.toFixed(2);
  document.querySelector("#acd").value = example.acd.toFixed(3);
  document.querySelector("#lt").value = example.lt.toFixed(3);
  document.querySelector("#wtw").value = example.wtw == null ? "" : example.wtw.toFixed(3);
  document.querySelector("#cct").value = example.cct == null ? "" : example.cct.toFixed(3);
  const exampleType = example.exampleType || (example.ageGroup
    ? `${example.ageGroup} ${example.referenceCategory}${example.modelTier ? ` ${example.modelTier}` : ""} reference`
    : example.referenceCategory
      ? `${example.referenceCategory} reference`
      : "Study case");
  exampleCaption.textContent = `${exampleType} ${example.caseId} · ${example.name} · ${exampleIndex + 1}/${BiometryOODExamples.examples.length}`;
  exampleCaption.hidden = false;
  validationMessage.textContent = "";
  updateModelPreview();
  if (modelBundle) showResult(BiometryOODCore.calculate(modelBundle, readInputs()));
}

exampleButton.addEventListener("click", loadExample);

resetButton.addEventListener("click", () => {
  form.reset();
  previousExampleIndex = null;
  exampleCaption.hidden = true;
  resetResults();
  updateModelPreview();
});

async function initialize() {
  try {
    const response = await fetch(MODEL_URL, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    modelBundle = await response.json();
    document.querySelector("#model-version").textContent = modelBundle.bundle_version;
    document.querySelector("#reference-patients").textContent = "Selected at calculation";
    document.querySelector("#derivation-patients").textContent = "Selected at calculation";
    document.querySelector("#age-range").textContent = "Continuous: 2–100 years";
    modelState.textContent = `${modelBundle.bundle_version} ready`;
    modelState.className = "model-state ready";
    calculateButton.disabled = false;
    exampleButton.disabled = false;
    updateModelPreview();
    const requestedExample = Number(new URLSearchParams(window.location.search).get("example"));
    if (Number.isInteger(requestedExample) && requestedExample >= 1) {
      loadExample(requestedExample - 1);
    }
  } catch (error) {
    modelState.textContent = "Model unavailable";
    modelState.className = "model-state error";
    validationMessage.textContent = `The reference model could not be loaded: ${error.message}`;
  }
}

initialize();
