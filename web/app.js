const MODEL_URL = "../models/biometry_ood_age_stratified_v2.json";

const form = document.querySelector("#calculator-form");
const calculateButton = document.querySelector("#calculate-button");
const exampleButton = document.querySelector("#example-button");
const resetButton = document.querySelector("#reset-button");
const validationMessage = document.querySelector("#validation-message");
const modelPreview = document.querySelector("#model-preview");
const modelState = document.querySelector("#model-state");
const resultEmpty = document.querySelector("#result-empty");
const resultContent = document.querySelector("#result-content");

let modelBundle = null;

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
  document.querySelector("#selected-model-detail").textContent = `${result.model.stratum_label} / ${result.model.tier}`;
  document.querySelector("#model-version").textContent = result.model.model_version;
  document.querySelector("#reference-eyes").textContent = result.model.reference_rows.toLocaleString();
  document.querySelector("#age-range").textContent = result.model.display_age_range;
  document.querySelector("#cohort-note").textContent = `${result.model.cohort_status} External and postoperative outcome validation are required before clinical decision-support use.`;
  document.querySelector("#track-marker").style.left = `${Math.min(100, Math.max(0, result.percentile))}%`;
  resultEmpty.hidden = true;
  resultContent.hidden = false;
}

function resetResults() {
  resultEmpty.hidden = false;
  resultContent.hidden = true;
  validationMessage.textContent = "";
}

function updateModelPreview() {
  if (!modelBundle) return;
  const selected = BiometryOODCore.selectModel(modelBundle, readInputs());
  modelPreview.textContent = selected
    ? `${selected.stratum_label} / ${selected.tier} model selected`
    : "No reference model is available for this age.";
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const values = readInputs();
  const error = BiometryOODCore.validate(modelBundle, values);
  validationMessage.textContent = error;
  if (error) return;
  showResult(BiometryOODCore.calculate(modelBundle, values));
});

form.addEventListener("input", updateModelPreview);

function loadExample() {
  document.querySelector("#age").value = "80";
  document.querySelector("#al").value = "23.61";
  document.querySelector("#mean-k").value = "40.80";
  document.querySelector("#acd").value = "1.94";
  document.querySelector("#lt").value = "5.58";
  document.querySelector("#wtw").value = "10.99";
  document.querySelector("#cct").value = "0.601";
  validationMessage.textContent = "";
  updateModelPreview();
}

exampleButton.addEventListener("click", loadExample);

resetButton.addEventListener("click", () => {
  form.reset();
  resetResults();
  updateModelPreview();
});

async function initialize() {
  try {
    const response = await fetch(MODEL_URL, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    modelBundle = await response.json();
    document.querySelector("#model-version").textContent = modelBundle.bundle_version;
    document.querySelector("#reference-eyes").textContent = "Selected at calculation";
    document.querySelector("#age-range").textContent = "Automatic: 2–100 years";
    modelState.textContent = `${modelBundle.bundle_version} ready`;
    modelState.className = "model-state ready";
    calculateButton.disabled = false;
    updateModelPreview();
    if (new URLSearchParams(window.location.search).get("example") === "1") {
      loadExample();
      showResult(BiometryOODCore.calculate(modelBundle, readInputs()));
    }
  } catch (error) {
    modelState.textContent = "Model unavailable";
    modelState.className = "model-state error";
    validationMessage.textContent = `The reference model could not be loaded: ${error.message}`;
  }
}

initialize();
