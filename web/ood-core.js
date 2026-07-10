(function attachBiometryOODCore(root) {
  function expectedByAge(model, name, age) {
    const adjustment = model.age_adjustment;
    const feature = adjustment.features[name];
    if (!feature) return null;
    const t = (age - adjustment.age_center_years) / adjustment.age_scale_years;
    const coefficients = feature.coefficients;
    return coefficients[0] + coefficients[1] * t + coefficients[2] * t * t;
  }

  function matrixVector(matrix, vector) {
    return matrix.map((row) => row.reduce((sum, value, index) => sum + value * vector[index], 0));
  }

  function percentileOf(sortedValues, value) {
    let low = 0;
    let high = sortedValues.length;
    while (low < high) {
      const middle = Math.floor((low + high) / 2);
      if (value < sortedValues[middle]) high = middle;
      else low = middle + 1;
    }
    return (100 * low) / sortedValues.length;
  }

  function modelsForAge(bundle, age) {
    return bundle.models.filter(
      (model) => age >= model.age_min_inclusive && age < model.age_max_exclusive,
    );
  }

  function inRange(model, name, value) {
    const range = model.input_ranges[name];
    return Number.isFinite(value) && value >= range[0] && value <= range[1];
  }

  function selectModel(bundle, values) {
    const candidates = modelsForAge(bundle, values.age);
    if (!candidates.length) return null;
    const extended = candidates.find((model) => model.tier === "Extended");
    if (inRange(extended, "WTW", values.wtw) && inRange(extended, "CCT", values.cct)) {
      return extended;
    }
    return candidates.find((model) => model.tier === "Core");
  }

  function validate(bundle, values) {
    if (!Number.isFinite(values.age)) return "Age is required.";
    const model = selectModel(bundle, values);
    if (!model) return "Age must be between 2 and 100.";
    const fields = [
      ["AL", values.al, model.input_ranges.AL],
      ["Mean K", values.meanK, model.input_ranges.Mean_K],
      ["ACD", values.acd, model.input_ranges.ACD],
      ["LT", values.lt, model.input_ranges.LT],
    ];
    for (const [label, value, range] of fields) {
      if (!Number.isFinite(value)) return `${label} is required.`;
      if (value < range[0] || value > range[1]) {
        return `${label} must be between ${range[0]} and ${range[1]}.`;
      }
    }
    return "";
  }

  function calculate(bundle, values) {
    const model = selectModel(bundle, values);
    if (!model) throw new Error("No OOD model is available for this age.");
    const expectedAcd = expectedByAge(model, "ACD", values.age);
    const expectedLt = expectedByAge(model, "LT", values.age);
    const adjustedAcd = values.acd - expectedAcd;
    const adjustedLt = values.lt - expectedLt;
    const source = {
      AL: values.al,
      Mean_K: values.meanK,
      ACD: values.acd,
      LT: values.lt,
      WTW: values.wtw,
      CCT: values.cct,
    };
    const vector = model.inputs.map((name) => {
      const expected = expectedByAge(model, name, values.age);
      return expected === null ? source[name] : source[name] - expected;
    });
    const delta = vector.map((value, index) => value - model.robust_location[index]);
    const projected = matrixVector(model.precision_matrix, delta);
    const distanceSquared = Math.max(
      0,
      delta.reduce((sum, value, index) => sum + value * projected[index], 0),
    );
    const distance = Math.sqrt(distanceSquared);
    const percentile = percentileOf(model.reference_distances, distance);

    let score = 0;
    let status = "Routine-range anatomy";
    let statusClass = "status-routine";
    const score0Upper = model.score_thresholds_percentile.score_0_upper;
    const score1Upper = model.score_thresholds_percentile.score_1_upper;
    if (percentile >= score1Upper) {
      score = 2;
      status = "Out-of-distribution anatomy";
      statusClass = "status-ood";
    } else if (percentile >= score0Upper) {
      score = 1;
      status = "Uncommon anatomy";
      statusClass = "status-uncommon";
    }

    const zScores = delta.map((value, index) => value / model.feature_standard_deviations[index]);
    const dominant = zScores
      .map((value, index) => ({ label: model.feature_labels[index], value }))
      .sort((a, b) => Math.abs(b.value) - Math.abs(a.value))
      .slice(0, 2)
      .map((item) => `${item.label} ${item.value >= 0 ? "+" : ""}${item.value.toFixed(1)} SD`)
      .join("; ");

    return {
      expectedAcd,
      expectedLt,
      adjustedAcd,
      adjustedLt,
      distance,
      percentile,
      score,
      status,
      statusClass,
      dominant,
      model,
    };
  }

  const api = { calculate, expectedByAge, percentileOf, selectModel, validate };
  root.BiometryOODCore = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
}(typeof globalThis !== "undefined" ? globalThis : this));
