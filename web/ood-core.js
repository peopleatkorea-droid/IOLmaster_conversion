(function attachBiometryOODCore(root) {
  function interpolate(value, anchors, values) {
    if (value <= anchors[0]) return values[0];
    if (value >= anchors[anchors.length - 1]) return values[values.length - 1];
    let upper = 1;
    while (upper < anchors.length && value > anchors[upper]) upper += 1;
    const lower = upper - 1;
    const fraction = (value - anchors[lower]) / (anchors[upper] - anchors[lower]);
    return values[lower] + fraction * (values[upper] - values[lower]);
  }

  function quantile(sortedValues, probability) {
    const position = (sortedValues.length - 1) * probability;
    const lower = Math.floor(position);
    const upper = Math.ceil(position);
    if (lower === upper) return sortedValues[lower];
    const fraction = position - lower;
    return sortedValues[lower] + fraction * (sortedValues[upper] - sortedValues[lower]);
  }

  function tailExpandedPosition(percentile) {
    const value = Math.min(100, Math.max(0, Number(percentile)));
    if (value <= 90) return (value / 90) * 65;
    if (value <= 97.5) return 65 + ((value - 90) / 7.5) * 22;
    return 87 + ((value - 97.5) / 2.5) * 13;
  }

  function expectedByAge(model, name, age) {
    const adjustment = model.age_adjustment;
    const feature = adjustment.features[name];
    if (!feature) return null;
    const t = (age - adjustment.age_center_years) / adjustment.age_scale_years;
    const coefficients = feature.coefficients;
    if (adjustment.basis === "linear hinge spline") {
      let result = coefficients[0] + coefficients[1] * t;
      adjustment.knots_years.forEach((knot, index) => {
        const scaledKnot = (knot - adjustment.age_center_years) / adjustment.age_scale_years;
        result += coefficients[index + 2] * Math.max(0, t - scaledKnot);
      });
      return result;
    }
    return coefficients[0] + coefficients[1] * t + coefficients[2] * t * t;
  }

  function scaleByAge(model, name, age, index) {
    const feature = model.age_adjustment.features[name] || {};
    if (feature.scale_anchors_years) {
      return interpolate(age, feature.scale_anchors_years, feature.scale_values);
    }
    return model.feature_scalers ? model.feature_scalers[index] : 1;
  }

  function matrixVector(matrix, vector) {
    return matrix.map((row) => row.reduce((sum, value, index) => sum + value * vector[index], 0));
  }

  function lowerBound(sortedValues, value) {
    let low = 0;
    let high = sortedValues.length;
    while (low < high) {
      const middle = Math.floor((low + high) / 2);
      if (sortedValues[middle] < value) low = middle + 1;
      else high = middle;
    }
    return low;
  }

  function upperBound(sortedValues, value) {
    let low = 0;
    let high = sortedValues.length;
    while (low < high) {
      const middle = Math.floor((low + high) / 2);
      if (value < sortedValues[middle]) high = middle;
      else low = middle + 1;
    }
    return low;
  }

  function percentileOf(sortedValues, value) {
    return (100 * upperBound(sortedValues, value)) / sortedValues.length;
  }

  function approximateFrequencyRange(tailProbability) {
    const frequency = Math.max(1, 1 / Math.max(tailProbability, 1e-12));
    let step = 100;
    if (frequency < 10) step = 1;
    else if (frequency < 50) step = 5;
    else if (frequency < 100) step = 10;
    else if (frequency < 250) step = 25;
    else if (frequency < 500) step = 50;
    const lower = Math.max(1, Math.round((frequency * 0.8) / step) * step);
    let upper = Math.max(lower, Math.round((frequency * 1.25) / step) * step);
    if (upper === lower) upper += step;
    return { lower, upper };
  }

  function calibrationWarning(calibration) {
    const warnings = [];
    if (calibration.maxPercentile < 97.5) {
      warnings.push(
        `Age-local calibration can reach at most ${calibration.maxPercentile.toFixed(1)} percentile at this age, so the Rare threshold is not attainable.`,
      );
    }
    if (calibration.effectiveN < 50) {
      warnings.push(
        `Age-local calibration effective N is ${calibration.effectiveN.toFixed(0)}; percentile precision is limited.`,
      );
    }
    return warnings.join(" ");
  }

  function calibratedPercentile(model, age, distance) {
    if (model.calibration_age_distance && model.age_calibration_bandwidth_years) {
      let totalWeight = 0;
      let belowWeight = 0;
      let squaredWeight = 0;
      const bandwidth = model.age_calibration_bandwidth_years;
      const clusterWeights = new Map();
      let hasClusters = false;
      model.calibration_age_distance.forEach((pair, pairIndex) => {
        const [calibrationAge, calibrationDistance] = pair;
        const clusterId = pair.length > 2 ? pair[2] : pairIndex;
        hasClusters = hasClusters || pair.length > 2;
        const standardizedAge = (calibrationAge - age) / bandwidth;
        const weight = Math.exp(-0.5 * standardizedAge * standardizedAge);
        totalWeight += weight;
        squaredWeight += weight * weight;
        clusterWeights.set(clusterId, (clusterWeights.get(clusterId) || 0) + weight);
        if (calibrationDistance < distance) belowWeight += weight;
      });
      const denominator = totalWeight + 1;
      const effectiveDenominator = hasClusters
        ? [...clusterWeights.values()].reduce((sum, weight) => sum + weight * weight, 0)
        : squaredWeight;
      return {
        percentile: (100 * belowWeight) / denominator,
        tailProbability: (1 + totalWeight - belowWeight) / denominator,
        effectiveN: effectiveDenominator ? (totalWeight * totalWeight) / effectiveDenominator : 0,
        maxPercentile: (100 * totalWeight) / denominator,
        ageLocal: true,
      };
    }
    const distances = model.calibration_distances || model.reference_distances;
    const percentile = (100 * upperBound(distances, distance)) / distances.length;
    return {
      percentile,
      tailProbability: Math.max(1 - percentile / 100, 1 / Math.max(1, distances.length)),
      effectiveN: distances.length,
      maxPercentile: 100,
      ageLocal: false,
    };
  }

  function raritySummary(percentile, tailProbability, ageLocal, referenceUnit = null) {
    if (percentile < 90) {
      return {
        value: "Common",
        caption: `Within the central 90% of ${referenceUnit || (ageLocal ? "age-weighted calibration eyes" : "reference eyes")}`,
      };
    }
    const { lower, upper } = approximateFrequencyRange(tailProbability);
    return {
      value: `~1 in ${lower}–${upper}`,
      caption: `${referenceUnit || (ageLocal ? "age-weighted calibration eyes" : "reference eyes")} is this unusual or more`,
    };
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

  function modelSelectionWarning(bundle, values) {
    const candidates = modelsForAge(bundle, values.age);
    if (!candidates.length) return "";
    const extended = candidates.find((model) => model.tier === "Extended");
    const optional = [
      ["WTW", values.wtw],
      ["CCT", values.cct],
    ];
    const provided = optional.filter(([, value]) => value !== null && value !== "");
    if (!provided.length) return "";

    const issues = [];
    const ignored = [];
    optional.forEach(([name, value]) => {
      if (value === null || value === "") {
        issues.push(`${name} is missing`);
        return;
      }
      if (!inRange(extended, name, value)) {
        const range = extended.input_ranges[name];
        issues.push(`${name} is outside ${range[0]}–${range[1]}`);
      } else {
        ignored.push(name);
      }
    });
    if (!issues.length) return "";
    const ignoredText = ignored.length ? ` Valid ${ignored.join(" and ")} input was ignored.` : "";
    return `Extended model not used: ${issues.join("; ")}.${ignoredText} Core model calculated.`;
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

  function calculateForModel(model, values) {
    const source = {
      AL: values.al,
      Mean_K: values.meanK,
      ACD: values.acd,
      LT: values.lt,
      WTW: values.wtw,
      CCT: values.cct,
    };
    const residuals = {};
    const vector = model.inputs.map((name, index) => {
      const expected = expectedByAge(model, name, values.age);
      residuals[name] = expected === null ? source[name] : source[name] - expected;
      return residuals[name] / scaleByAge(model, name, values.age, index);
    });
    const delta = vector.map((value, index) => value - model.robust_location[index]);
    const projected = matrixVector(model.precision_matrix, delta);
    const distanceSquared = Math.max(
      0,
      delta.reduce((sum, value, index) => sum + value * projected[index], 0),
    );
    const distance = Math.sqrt(distanceSquared);
    const calibration = calibratedPercentile(model, values.age, distance);
    const percentile = calibration.percentile;

    let status = "Typical anatomy";
    let statusClass = "status-routine";
    const score0Upper = model.score_thresholds_percentile.score_0_upper;
    const score1Upper = model.score_thresholds_percentile.score_1_upper;
    if (percentile >= score1Upper) {
      status = "Rare anatomy";
      statusClass = "status-ood";
    } else if (percentile >= score0Upper) {
      status = "Uncommon anatomy";
      statusClass = "status-uncommon";
    }

    const zScores = delta.map((value, index) => value / model.feature_standard_deviations[index]);
    const dominant = zScores
      .map((value, index) => ({ label: model.feature_labels[index], value }))
      .sort((a, b) => Math.abs(b.value) - Math.abs(a.value))
      .slice(0, 2)
      .map((item) => `${item.label.replace(/ vs age$/, "")} ${item.value >= 0 ? "+" : ""}${item.value.toFixed(1)} SD`)
      .join("; ");

    const units = { AL: "mm", Mean_K: "D", ACD: "mm", LT: "mm", WTW: "mm", CCT: "mm" };
    const labels = { AL: "AL", Mean_K: "Mean K", ACD: "ACD", LT: "LT", WTW: "WTW", CCT: "CCT" };
    const profile = model.inputs.flatMap((name, index) => {
      const reference = model.marginal_reference_values && model.marginal_reference_values[name];
      if (!reference) return [];
      return [{
        name,
        label: labels[name],
        unit: units[name],
        observed: source[name],
        residual: residuals[name],
        standardizedValue: vector[index],
        marginalPercentile: (100 * lowerBound(reference, vector[index])) / (reference.length + 1),
        q2_5: quantile(reference, 0.025),
        q25: quantile(reference, 0.25),
        q50: quantile(reference, 0.50),
        q75: quantile(reference, 0.75),
        q97_5: quantile(reference, 0.975),
      }];
    });

    return {
      expectedAcd: expectedByAge(model, "ACD", values.age),
      expectedLt: expectedByAge(model, "LT", values.age),
      adjustedAcd: residuals.ACD,
      adjustedLt: residuals.LT,
      distance,
      percentile,
      status,
      statusClass,
      dominant,
      rarity: raritySummary(
        percentile,
        calibration.tailProbability,
        calibration.ageLocal,
        model.reference_unit || null,
      ),
      effectiveN: calibration.effectiveN,
      maxPercentile: calibration.maxPercentile,
      calibrationWarning: calibrationWarning(calibration),
      calibration,
      profile,
      model,
      coreSensitivity: null,
    };
  }

  function calculate(bundle, values) {
    const model = selectModel(bundle, values);
    if (!model) throw new Error("No OOD model is available for this age.");
    const result = calculateForModel(model, values);
    result.modelSelectionWarning = modelSelectionWarning(bundle, values);
    if (model.tier === "Extended") {
      const core = modelsForAge(bundle, values.age).find((candidate) => candidate.tier === "Core");
      const coreResult = calculateForModel(core, values);
      result.coreSensitivity = {
        percentile: coreResult.percentile,
        status: coreResult.status,
        difference: result.percentile - coreResult.percentile,
      };
    }
    return result;
  }

  const api = {
    calculate,
    calculateForModel,
    calibratedPercentile,
    calibrationWarning,
    expectedByAge,
    percentileOf,
    raritySummary,
    modelSelectionWarning,
    selectModel,
    tailExpandedPosition,
    validate,
  };
  root.BiometryOODCore = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
}(typeof globalThis !== "undefined" ? globalThis : this));
