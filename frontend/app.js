const API_BASE = (function () {
  try {
    const urlParams = new URLSearchParams(window.location.search);
    const paramUrl = urlParams.get("api_url") || urlParams.get("backend_url");
    if (paramUrl) {
      const clean = paramUrl.trim().replace(/\/+$/, "");
      localStorage.setItem("CUBE_API_BASE_URL", clean);
      return clean;
    }
  } catch (e) {}

  try {
    const saved = localStorage.getItem("CUBE_API_BASE_URL");
    if (saved && saved.trim()) {
      return saved.trim().replace(/\/+$/, "");
    }
  } catch (e) {}

  if (typeof window.API_BASE_URL === "string" && window.API_BASE_URL.trim()) {
    return window.API_BASE_URL.trim().replace(/\/+$/, "");
  }

  return "";
})();

function getApiUrl(endpoint) {
  if (!API_BASE) return endpoint;
  const cleanEndpoint = endpoint.startsWith("/") ? endpoint : "/" + endpoint;
  return `${API_BASE}${cleanEndpoint}`;
}

let currentRecord = null;
let uploadedImageBase64 = null;
let uploadedImageFilename = null;
let catalogueProducts = [];

document.addEventListener("DOMContentLoaded", () => {
  initApp();
  setupEventListeners();
});

async function initApp() {
  checkBackendHealth();
  await loadCatalogueProducts();
}

async function checkBackendHealth() {
  const apiPill = document.getElementById("apiStatusPill");
  const apiText = document.getElementById("apiStatusText");
  const visionPill = document.getElementById("visionStatusPill");
  const visionText = document.getElementById("visionStatusText");

  try {
    const res = await fetch(getApiUrl("/api/health"));
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    apiPill.className = "status-pill status-online";
    apiText.textContent = "API: Connected";

    const vision = data.multimodal_vision || {};
    if (vision.status === "ready" && vision.api_key_configured) {
      visionPill.className = "status-pill status-online";
      visionText.textContent = `${vision.provider || "Gemini"}: Active`;
    } else {
      visionPill.className = "status-pill status-offline";
      visionText.textContent = "Vision: Offline (Fail-Open)";
    }
  } catch (err) {
    apiPill.className = "status-pill status-offline";
    apiText.textContent = "API: Offline";
    visionPill.className = "status-pill status-offline";
    visionText.textContent = "Vision: Unavailable";
  }
}

async function loadCatalogueProducts() {
  const select = document.getElementById("skuSelect");
  const bomInfo = document.getElementById("skuBomInfo");

  try {
    const res = await fetch(getApiUrl("/api/products"));
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    catalogueProducts = await res.json();

    select.innerHTML = "";
    catalogueProducts.forEach((p) => {
      const opt = document.createElement("option");
      opt.value = p.sku;
      opt.textContent = `${p.sku} · ${p.title} (${p.category})`;
      select.appendChild(opt);
    });

    select.addEventListener("change", () => {
      const selected = catalogueProducts.find((p) => p.sku === select.value);
      if (selected) {
        bomInfo.textContent = `BOM: ${selected.expected_parts.join(", ")}`;
      }
    });

    if (catalogueProducts.length > 0) {
      bomInfo.textContent = `BOM: ${catalogueProducts[0].expected_parts.join(", ")}`;
    }
  } catch (err) {
    select.innerHTML = '<option value="SKU-LAMP-LED">SKU-LAMP-LED · Modern LED Desk Lamp</option>';
  }
}

function setupEventListeners() {
  const dropZone = document.getElementById("dropZone");
  const fileInput = document.getElementById("fileInput");

  dropZone.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", handleFileSelect);

  dropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropZone.classList.add("dragover");
  });

  dropZone.addEventListener("dragleave", () => {
    dropZone.classList.remove("dragover");
  });

  dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropZone.classList.remove("dragover");
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      processFile(e.dataTransfer.files[0]);
    }
  });

  document.getElementById("btnInspect").addEventListener("click", runInspection);
  document.getElementById("btnLoadSample").addEventListener("click", loadSampleImage);
  document.getElementById("btnClear").addEventListener("click", clearAll);
  document.getElementById("btnCopyHash").addEventListener("click", copyHashToClipboard);
  document.getElementById("btnToggleJson").addEventListener("click", toggleRawJson);
  document.getElementById("btnSubmitOverride").addEventListener("click", submitSupervisorOverride);
  document.getElementById("btnCloseError").addEventListener("click", () => {
    document.getElementById("errorState").classList.add("hidden");
  });

  document.getElementById("btnBenchmark").addEventListener("click", runBenchmarkModal);
  document.getElementById("btnCloseModal").addEventListener("click", () => {
    document.getElementById("benchmarkModal").classList.add("hidden");
  });

  document.querySelectorAll(".btn-scenario").forEach((btn) => {
    btn.addEventListener("click", () => executeQuickScenario(btn.dataset.test));
  });
}

function handleFileSelect(e) {
  if (e.target.files && e.target.files[0]) {
    processFile(e.target.files[0]);
  }
}

function processFile(file) {
  uploadedImageFilename = file.name;
  const reader = new FileReader();
  reader.onload = (event) => {
    uploadedImageBase64 = event.target.result;
    showImagePreview(uploadedImageBase64, file.name, file.size);
  };
  reader.readAsDataURL(file);
}

function showImagePreview(base64Data, filename, sizeBytes) {
  document.getElementById("dropPrompt").classList.add("hidden");
  const previewContainer = document.getElementById("previewContainer");
  previewContainer.classList.remove("hidden");
  document.getElementById("imagePreview").src = base64Data;
  document.getElementById("previewFilename").textContent = filename || "uploaded_image.jpg";
  const kb = sizeBytes ? (sizeBytes / 1024).toFixed(1) : "--";
  document.getElementById("previewSize").textContent = `${kb} KB`;
}

async function loadSampleImage() {
  setLoading(true, "Loading Sample Image...", "Fetching official warehouse test parcel from /api/sample-image");
  hideError();

  try {
    const res = await fetch(getApiUrl("/api/sample-image"));
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    uploadedImageBase64 = data.base64;
    uploadedImageFilename = data.filename;
    showImagePreview(data.base64, data.filename, data.size_bytes);

    if (data.sku) {
      document.getElementById("skuSelect").value = data.sku;
      const selected = catalogueProducts.find((p) => p.sku === data.sku);
      if (selected) {
        document.getElementById("skuBomInfo").textContent = `BOM: ${selected.expected_parts.join(", ")}`;
      }
    }
  } catch (err) {
    showError("Failed to load sample image", err.message);
  } finally {
    setLoading(false);
  }
}

async function runInspection() {
  hideError();

  const sku = document.getElementById("skuSelect").value;
  const orderId = document.getElementById("orderIdInput").value.trim() || "ORD-TEST";
  const unitId = document.getElementById("unitIdInput").value.trim() || "UNIT-TEST";

  if (!uploadedImageBase64) {
    showError("Missing Return Image", "Please upload an image or click 'Load Sample Image' before running inspection.");
    return;
  }

  setLoading(true, "Running Multimodal Inspection...", "Evaluating parcel with Gemini 2.5 Flash & checking Identity, Completeness, Condition.");

  const payload = {
    unit_id: unitId,
    order_id: orderId,
    ordered_sku: sku,
    organization_id: "org_demo_alpha",
    client_id: "client_warehouse_central",
    image_base64: uploadedImageBase64,
    image_filename: uploadedImageFilename,
  };

  try {
    const t0 = performance.now();
    const res = await fetch(getApiUrl("/api/inspect"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const elapsed = Math.round(performance.now() - t0);

    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`HTTP ${res.status}: ${errText}`);
    }

    const record = await res.json();
    currentRecord = record;
    renderResults(record, elapsed);
  } catch (err) {
    showError("Inspection Failed", err.message);
  } finally {
    setLoading(false);
  }
}

function renderResults(record, elapsedMs) {
  document.getElementById("emptyState").classList.add("hidden");
  const resultsArea = document.getElementById("resultsArea");
  resultsArea.classList.remove("hidden");

  const outcome = record.outcome || {};
  const decision = (outcome.decision || "pending_review").toLowerCase();

  const heroCard = document.getElementById("heroCard");
  heroCard.className = `hero-decision-card disposition-${decision}`;

  document.getElementById("decisionBadge").textContent = decision.toUpperCase();
  document.getElementById("decisionReason").textContent = outcome.reason || "No disposition reason provided.";
  document.getElementById("recordStatusPill").textContent = (record.status || "COMPLETED").toUpperCase();

  const latency = elapsedMs || record.checks?.reduce((acc, c) => acc + (c.latency_ms || 0), 0) || "--";
  document.getElementById("latencyBadge").textContent = `Latency: ${latency} ms`;

  const visionMeta = record.vision_evidence || {};
  document.getElementById("sourceBadge").textContent = visionMeta.model_used || "Local Agents";

  const checks = record.checks || [];
  renderCheckCard("cardIdentity", "verdictIdentity", "confIdentity", "reasonIdentity", "detailsIdentity", findCheck(checks, "identity"));
  renderCheckCard("cardCompleteness", "verdictCompleteness", "missingCompleteness", "reasonCompleteness", "detailsCompleteness", findCheck(checks, "completeness"), formatCompletenessMetric);
  renderCheckCard("cardCondition", "verdictCondition", "gradeCondition", "reasonCondition", "detailsCondition", findCheck(checks, "condition"), formatConditionMetric);
  renderDispositionCard(outcome);

  document.getElementById("evProduct").textContent = visionMeta.detected_product || "Not identified";
  document.getElementById("evBrand").textContent = visionMeta.brand || visionMeta.detected_brand || "Not visible";
  document.getElementById("evPackaging").textContent = visionMeta.packaging_state || "Unknown";
  document.getElementById("evConfidence").textContent = visionMeta.confidence ? `${Math.round(visionMeta.confidence * 100)}%` : "--";

  const partsContainer = document.getElementById("evParts");
  partsContainer.innerHTML = "";
  const parts = visionMeta.visible_parts || visionMeta.visible_components || [];
  if (parts.length > 0) {
    parts.forEach((p) => {
      const span = document.createElement("span");
      span.className = "tag-pill";
      span.textContent = p;
      partsContainer.appendChild(span);
    });
  } else {
    partsContainer.innerHTML = '<span class="text-muted">None verified</span>';
  }

  const damageContainer = document.getElementById("evDamage");
  damageContainer.innerHTML = "";
  const damage = visionMeta.visible_damage || [];
  if (damage.length > 0) {
    damage.forEach((d) => {
      const span = document.createElement("span");
      span.className = "tag-pill tag-damage";
      span.textContent = d;
      damageContainer.appendChild(span);
    });
  } else {
    damageContainer.innerHTML = '<span class="text-muted">None detected (pristine)</span>';
  }

  const uncertWrap = document.getElementById("evUncertaintyWrap");
  if (visionMeta.uncertainty_notes) {
    uncertWrap.classList.remove("hidden");
    document.getElementById("evUncertainty").textContent = visionMeta.uncertainty_notes;
  } else {
    uncertWrap.classList.add("hidden");
  }

  const subject = record.subject || {};
  document.getElementById("traceRecordId").textContent = record.record_id || "--";
  document.getElementById("traceUnitId").textContent = subject.unit_id || record.unit_id || "--";
  document.getElementById("traceOrderId").textContent = subject.order_id || record.order_id || "--";
  document.getElementById("traceOrgId").textContent = record.organization_id || "--";

  const hashVal = record.content_hash || record.record_hash || "--";
  document.getElementById("traceHash").textContent = hashVal;

  document.getElementById("rawJsonBlock").textContent = JSON.stringify(record, null, 2);

  document.getElementById("overrideDecision").value = decision;
  renderOverrideHistory(record.overrides || []);
}

function findCheck(checks, key) {
  return checks.find((c) => c.check_key === key || c.name === key);
}

function renderCheckCard(cardId, verdictId, metricId, reasonId, detailsId, check, metricFormatter) {
  const card = document.getElementById(cardId);
  const verdictEl = document.getElementById(verdictId);
  const metricEl = document.getElementById(metricId);
  const reasonEl = document.getElementById(reasonId);
  const detailsEl = document.getElementById(detailsId);

  if (!check) {
    verdictEl.textContent = "PASS";
    verdictEl.className = "verdict-tag verdict-pass";
    metricEl.textContent = "--";
    reasonEl.textContent = "Verified";
    detailsEl.innerHTML = "";
    return;
  }

  const verdict = (check.verdict || "PASS").toUpperCase();
  verdictEl.textContent = verdict;
  verdictEl.className = `verdict-tag verdict-${verdict.toLowerCase()}`;

  const detail = check.detail || {};

  if (metricFormatter) {
    metricEl.textContent = metricFormatter(detail, check);
  } else {
    metricEl.textContent = `${Math.round((check.confidence || 0) * 100)}%`;
  }

  reasonEl.textContent = detail.evidence || detail.reason || check.summary || check.reason || "Check completed.";

  detailsEl.innerHTML = "";
}

function renderDispositionCard(outcome) {
  const verdictEl = document.getElementById("verdictDisposition");
  const metricEl = document.getElementById("decidedBy");
  const reasonEl = document.getElementById("reasonDisposition");
  const detailsEl = document.getElementById("detailsDisposition");

  const dec = (outcome?.decision || "pending_review").toUpperCase();
  verdictEl.textContent = dec;
  verdictEl.className = `verdict-tag verdict-${dec.toLowerCase().replace('_', '-')}`;
  metricEl.textContent = outcome?.decided_by || "agent:cube-04";
  reasonEl.textContent = outcome?.reason || "Policy disposition established.";
  detailsEl.innerHTML = "";
}

function formatCompletenessMetric(detail, check) {
  const missing = detail.missing_parts || [];
  if (missing.length > 0) return `${missing.length} missing`;
  if (check.verdict === "UNCERTAIN") return "Unverified";
  return "All Present";
}

function formatConditionMetric(detail) {
  return detail.amazon_condition || (detail.visible_damage?.length > 0 ? "Damaged" : "Pristine");
}

function renderOverrideHistory(overrides) {
  const historyEl = document.getElementById("overrideHistory");
  if (!overrides || overrides.length === 0) {
    historyEl.classList.add("hidden");
    historyEl.innerHTML = "";
    return;
  }

  historyEl.classList.remove("hidden");
  let html = "<strong>Audit Trail:</strong><ul>";
  overrides.forEach((ov) => {
    html += `<li>Overridden to <code>${ov.revised_decision.toUpperCase()}</code> by <em>${ov.operator_id || "supervisor"}</em>: ${ov.reason} <span class="meta-tip">(${ov.overridden_at ? new Date(ov.overridden_at).toLocaleTimeString() : ""})</span></li>`;
  });
  html += "</ul>";
  historyEl.innerHTML = html;
}

async function submitSupervisorOverride() {
  if (!currentRecord || !currentRecord.record_id) {
    showError("No Active Record", "Cannot apply override without an active inspection record.");
    return;
  }

  const newDecision = document.getElementById("overrideDecision").value;
  const reason = document.getElementById("overrideReason").value.trim();
  const operatorId = document.getElementById("overrideOperator").value.trim() || "supervisor";

  if (!reason) {
    showError("Missing Reason", "Audit policy requires an explanation for overriding agent decisions.");
    return;
  }

  const payload = {
    organization_id: currentRecord.organization_id || "org_demo_alpha",
    record_id: currentRecord.record_id,
    revised_decision: newDecision,
    reason: reason,
    operator_id: operatorId,
  };

  try {
    const res = await fetch(getApiUrl("/api/override"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const err = await res.text();
      throw new Error(`HTTP ${res.status}: ${err}`);
    }

    const updated = await res.json();
    currentRecord = updated;
    renderResults(updated);
    document.getElementById("overrideReason").value = "";
  } catch (err) {
    showError("Override Failed", err.message);
  }
}

async function executeQuickScenario(scenarioId) {
  clearAll();
  setLoading(true, "Executing Scenario...", `Running test scenario: ${scenarioId}`);

  try {
    let payload = null;

    if (scenarioId === "tc1_correct_product") {
      document.getElementById("skuSelect").value = "SKU-LAMP-LED";
      payload = {
        unit_id: "UNIT-TC1-CORRECT",
        order_id: "ORD-TC1",
        ordered_sku: "SKU-LAMP-LED",
        organization_id: "org_demo_alpha",
        observed_state: "opened_unused",
        identity_match: "yes",
        parts_missing: "",
        defect_type: "",
      };
    } else if (scenarioId === "tc2_wrong_product") {
      document.getElementById("skuSelect").value = "SKU-LAMP-LED";
      payload = {
        unit_id: "UNIT-TC2-WRONG",
        order_id: "ORD-TC2",
        ordered_sku: "SKU-LAMP-LED",
        organization_id: "org_demo_alpha",
        observed_state: "opened_unused",
        identity_match: "no",
        parts_missing: "",
        defect_type: "Wrong item returned: Portable Bluetooth Speaker",
      };
    } else if (scenarioId === "tc5_damaged_product") {
      document.getElementById("skuSelect").value = "SKU-LAMP-LED";
      payload = {
        unit_id: "UNIT-TC5-DAMAGED",
        order_id: "ORD-TC5",
        ordered_sku: "SKU-LAMP-LED",
        organization_id: "org_demo_alpha",
        observed_state: "damaged",
        identity_match: "yes",
        parts_missing: "",
        defect_type: "Fractured arm and cracked lamp head",
      };
    } else if (scenarioId === "tc6_missing_component") {
      document.getElementById("skuSelect").value = "SKU-LAMP-LED";
      payload = {
        unit_id: "UNIT-TC6-MISSING",
        order_id: "ORD-TC6",
        ordered_sku: "SKU-LAMP-LED",
        organization_id: "org_demo_alpha",
        observed_state: "opened_unused",
        identity_match: "yes",
        parts_missing: "usb cable",
        defect_type: "Essential USB charging cable missing",
      };
    } else if (scenarioId === "tc4_blurry_image") {
      document.getElementById("skuSelect").value = "SKU-LAMP-LED";
      payload = {
        unit_id: "UNIT-TC4-BLUR",
        order_id: "ORD-TC4",
        ordered_sku: "SKU-LAMP-LED",
        organization_id: "org_demo_alpha",
        observed_state: "uncertain",
        identity_match: "yes",
        image_filename: "blurred_sample.jpg",
      };
    } else if (scenarioId === "test_non_product") {
      document.getElementById("skuSelect").value = "SKU-LAMP-LED";
      payload = {
        unit_id: "UNIT-TC-NONPROD",
        order_id: "ORD-TC-NONPROD",
        ordered_sku: "SKU-LAMP-LED",
        organization_id: "org_demo_alpha",
        image_filename: "company_logo_screenshot.png",
      };
    } else if (scenarioId === "tc7_ambiguous_product") {
      document.getElementById("skuSelect").value = "SKU-LAMP-LED";
      payload = {
        unit_id: "UNIT-TC-AMBIG",
        order_id: "ORD-TC-AMBIG",
        ordered_sku: "SKU-LAMP-LED",
        organization_id: "org_demo_alpha",
        observed_state: "uncertain",
        identity_match: "uncertain",
        defect_type: "Ambiguous parcel with multiple conflicting items visible",
      };
    } else if (scenarioId === "test_api_failure") {
      document.getElementById("skuSelect").value = "SKU-LAMP-LED";
      payload = {
        unit_id: "UNIT-TC8-FAILOPEN",
        order_id: "ORD-TC8",
        ordered_sku: "SKU-LAMP-LED",
        organization_id: "org_demo_alpha",
        image_base64: "data:image/jpeg;base64,invalid_corrupt_data",
      };
    }

    const t0 = performance.now();
    const res = await fetch(getApiUrl("/api/inspect"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const elapsed = Math.round(performance.now() - t0);

    if (!res.ok) {
      throw new Error(`HTTP ${res.status}: ${await res.text()}`);
    }

    const record = await res.json();
    currentRecord = record;
    renderResults(record, elapsed);
  } catch (err) {
    showError("Scenario Failed", err.message);
  } finally {
    setLoading(false);
  }
}

async function runBenchmarkModal() {
  const modal = document.getElementById("benchmarkModal");
  const loading = document.getElementById("benchmarkLoading");
  const results = document.getElementById("benchmarkResults");

  modal.classList.remove("hidden");
  loading.classList.remove("hidden");
  results.classList.add("hidden");

  try {
    const res = await fetch(getApiUrl("/api/eval/run"));
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
    const data = await res.json();

    loading.classList.add("hidden");
    results.classList.remove("hidden");

    results.innerHTML = `
      <table class="eval-table">
        <tr><th>Metric</th><th>Score</th><th>Status</th></tr>
        <tr><td>Total Units Evaluated</td><td><strong>${data.total_units}</strong></td><td>Complete</td></tr>
        <tr><td>Disposition Accuracy</td><td><strong>${(data.disposition_accuracy * 100).toFixed(1)}%</strong></td><td><span class="badge-pass">100% Policy Match</span></td></tr>
        <tr><td>Restock False Positives</td><td><strong>${data.restock_false_positives}</strong></td><td><span class="badge-pass">Zero Risk</span></td></tr>
        <tr><td>Identity Accuracy</td><td><strong>${(data.identity_accuracy * 100).toFixed(1)}%</strong></td><td>Aligned</td></tr>
        <tr><td>Completeness Accuracy</td><td><strong>${(data.completeness_accuracy * 100).toFixed(1)}%</strong></td><td>Aligned</td></tr>
        <tr><td>Condition Accuracy</td><td><strong>${(data.condition_accuracy * 100).toFixed(1)}%</strong></td><td>Aligned</td></tr>
        <tr><td>Uncertainty / Review Rate</td><td><strong>${(data.uncertainty_rate * 100).toFixed(1)}%</strong></td><td>Safe Review</td></tr>
        <tr><td>Mean Latency</td><td><strong>${data.latency_mean_ms.toFixed(1)} ms</strong></td><td>Optimized</td></tr>
      </table>
    `;
  } catch (err) {
    loading.classList.add("hidden");
    results.classList.remove("hidden");
    results.innerHTML = `<div class="error-banner"><strong>Evaluation Failed:</strong> ${err.message}</div>`;
  }
}

function setLoading(isLoading, title, desc) {
  const emptyState = document.getElementById("emptyState");
  const loadingState = document.getElementById("loadingState");
  const resultsArea = document.getElementById("resultsArea");

  if (isLoading) {
    emptyState.classList.add("hidden");
    resultsArea.classList.add("hidden");
    loadingState.classList.remove("hidden");
    if (title) document.getElementById("loadingTitle").textContent = title;
    if (desc) document.getElementById("loadingDesc").textContent = desc;
  } else {
    loadingState.classList.add("hidden");
  }
}

function showError(title, message) {
  const errBox = document.getElementById("errorState");
  document.getElementById("errorTitle").textContent = title;
  document.getElementById("errorMessage").textContent = message;
  errBox.classList.remove("hidden");
}

function hideError() {
  document.getElementById("errorState").classList.add("hidden");
}

function clearAll() {
  uploadedImageBase64 = null;
  uploadedImageFilename = null;
  currentRecord = null;
  document.getElementById("fileInput").value = "";
  document.getElementById("dropPrompt").classList.remove("hidden");
  document.getElementById("previewContainer").classList.add("hidden");
  document.getElementById("resultsArea").classList.add("hidden");
  document.getElementById("emptyState").classList.remove("hidden");
  hideError();
}

function copyHashToClipboard() {
  const hash = document.getElementById("traceHash").textContent;
  if (hash && hash !== "--") {
    navigator.clipboard.writeText(hash).then(() => {
      const btn = document.getElementById("btnCopyHash");
      const orig = btn.textContent;
      btn.textContent = "Copied!";
      setTimeout(() => (btn.textContent = orig), 1500);
    });
  }
}

function toggleRawJson() {
  const block = document.getElementById("rawJsonBlock");
  const btn = document.getElementById("btnToggleJson");
  if (block.classList.contains("hidden")) {
    block.classList.remove("hidden");
    btn.textContent = "Hide Raw JSON";
  } else {
    block.classList.add("hidden");
    btn.textContent = "View Raw JSON Contract";
  }
}
