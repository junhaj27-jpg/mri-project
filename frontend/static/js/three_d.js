const threeState = {
  status: null,
  series: [],
  meshPreviewText: "",
  reliableMask: false,
  regions: [],
};

const $3 = (id) => document.getElementById(id);

function syncFinalMeshButton() {
  $3("meshButton").disabled = !threeState.reliableMask;
}

async function loadThreeSeriesList() {
  const data = await apiGet("/api/series");
  threeState.series = data.series || [];
  $3("seriesSelect").innerHTML = "";
  for (const item of threeState.series) {
    const option = document.createElement("option");
    option.value = item.key;
    option.textContent = `${item.description || "Series"} | ${item.file_count} files | ${item.shape || ""}`;
    $3("seriesSelect").appendChild(option);
  }
}

async function refreshThreeStatus() {
  const status = await apiGet("/api/status");
  const meshStatus = await apiGet("/api/mesh-status");
  threeState.status = status;
  threeState.reliableMask = Boolean(status.reliable_mask);
  $3("sourceText").textContent = status.source || "-";
  $3("shapeText").textContent = formatShape(status.shape);
  $3("spacingText").textContent = formatSpacing(status.spacing);
  $3("sliceCountText").textContent = String(status.slice_count || "-");
  $3("seriesText").textContent = status.info?.SeriesDescription || status.source_label || "-";
  $3("hdbetInstalledText").textContent = String(Boolean(status.hdbet_installed));
  $3("synthstripAvailableText").textContent = String(Boolean(status.synthstrip_available));
  $3("maskSourceText").textContent = status.mask_source || "none";
  $3("maskStatusText").textContent = status.mask_status || "missing";
  $3("reliableMaskText").textContent = String(threeState.reliableMask);
  $3("maskShapeText").textContent = formatShape(status.mask_shape);
  $3("maskSumText").textContent = String(status.mask_sum ?? "-");
  $3("maskRatioText").textContent = String(status.mask_ratio ?? "-");
  $3("maskUniqueText").textContent = Array.isArray(status.mask_unique_values) ? status.mask_unique_values.join(", ") : "-";
  $3("inputNiftiPathText").textContent = status.input_nifti_path || "-";
  $3("brainMaskPathText").textContent = status.brain_mask_path || "-";
  $3("brainOnlyPathText").textContent = status.brain_only_path || "-";
  $3("meshPathText").textContent = status.final_mesh_path || status.mesh_path || "-";
  $3("debugMeshPathText").textContent = status.debug_mesh_path || "-";
  $3("lastErrorText").textContent = status.last_error || "-";
  updateRegionStatus(status.region_segmentation || {});
  $3("meshButton").disabled = !threeState.reliableMask;
  $3("surfaceTitle").textContent = threeState.reliableMask
    ? "Stable brain mask surface"
    : "Debug threshold mask preview - not final brain extraction";
  $3("maskWarningText").textContent = threeState.reliableMask
    ? ""
    : "DEBUG ONLY: threshold mask, not brain extraction";
  $3("meshText").textContent = meshStatus.status || (status.mesh_available ? "3D mesh loaded" : "No mesh generated yet");
  if (meshStatus.mesh_available) {
    loadMeshPreview();
  } else if (meshStatus.debug_mesh_available && !threeState.reliableMask) {
    setMeshFrameMessage("Brain mask is debug only. Final 3D disabled.", "warn");
  } else if (!threeState.reliableMask) {
    setMeshFrameMessage("Brain mask is debug only. Final 3D disabled.", "warn");
  } else {
    setMeshFrameMessage("No mesh generated yet", "info");
  }
  if (status.disclaimer) $3("disclaimer").textContent = status.disclaimer;
  updateThreeSliceLimit();
  syncFinalMeshButton();
}

async function loadThreeVolume() {
  setBusy(true);
  try {
    const key = encodeURIComponent($3("seriesSelect").value);
    await apiGet(`/api/load?series_key=${key}`);
    await refreshThreeStatus();
    await refreshThreeSlice();
    $3("maskText").textContent = "not checked";
    $3("maskShapeText").textContent = "-";
    $3("maskSumText").textContent = "-";
    $3("maskRatioText").textContent = "-";
    $3("maskUniqueText").textContent = "-";
    $3("componentCountText").textContent = "-";
    $3("largestComponentText").textContent = "-";
    $3("holeRatioText").textContent = "-";
    $3("edgeLeakageText").textContent = "-";
  } finally {
    setBusy(false);
    syncFinalMeshButton();
  }
}

function updateThreeSliceLimit() {
  const shape = threeState.status?.shape;
  if (!shape) return;
  const plane = $3("planeSelect").value;
  const max = Math.max(0, planeLength(shape, plane) - 1);
  $3("sliceRange").max = String(max);
  const current = Math.min(Number($3("sliceRange").value), max);
  $3("sliceRange").value = String(current);
  $3("sliceValueLabel").textContent = String(current);
}

async function refreshThreeSlice() {
  updateThreeSliceLimit();
  const plane = $3("planeSelect").value;
  const index = Number($3("sliceRange").value);
  const mask = $3("maskToggle").value;
  const regionOverlay = $3("regionOverlayToggle").value;
  if (regionOverlay !== "0") {
    const region = encodeURIComponent($3("regionSelect").value);
    const mode = regionOverlay === "all" ? "all" : "selected";
    $3("sliceImage").src = `/api/regions/overlay?plane=${encodeURIComponent(plane)}&index=${index}&region=${region}&mode=${mode}&t=${Date.now()}`;
  } else {
    $3("sliceImage").src = `/api/slice?plane=${encodeURIComponent(plane)}&index=${index}&mask=${mask}&t=${Date.now()}`;
  }
}

async function generateMesh() {
  setBusy(true);
  try {
    if (!threeState.reliableMask) {
      const mask = await apiGet("/api/mask");
      threeState.reliableMask = Boolean(mask.reliable_mask || mask.reliable_for_3d);
      $3("maskSourceText").textContent = mask.mask_source || "none";
      $3("maskStatusText").textContent = mask.mask_status || "-";
      $3("meshText").textContent = mask.status_warning
        || "Reliable skull stripping is not available. Current mask is threshold debug only. Final 3D brain mesh is disabled.";
      setMeshFrameMessage("Brain mask is debug only. Final 3D disabled.", "warn");
      if (!threeState.reliableMask) return;
    }
    const { sigma, smooth, downsample } = meshParams();
    setMeshFrameMessage("Building 3D mesh...", "info");
    const meta = await apiGet(`/api/build-mesh?sigma=${sigma}&smooth=${smooth}&downsample=${downsample}&step=1`);
    if (meta.ok === false) {
      threeState.reliableMask = false;
      const message = meta.message || meta.warning || "Mesh generation failed";
      $3("meshText").textContent = message;
      $3("lastErrorText").textContent = message;
      setMeshFrameMessage(`Mesh generation failed: ${message}`, "error");
      return;
    }
    threeState.meshPreviewText = `3D mesh loaded: ${meta.vertices} vertices / ${meta.faces} faces`;
    $3("meshText").textContent = threeState.meshPreviewText;
    $3("meshPathText").textContent = meta.mesh_path || "-";
    $3("debugMeshPathText").textContent = "-";
    loadMeshPreview();
  } finally {
    setBusy(false);
    syncFinalMeshButton();
  }
}

async function generateMask() {
  setBusy(true);
  try {
    const mask = await apiGet("/api/mask");
    const source = mask.mask_source || "none";
    threeState.reliableMask = Boolean(mask.reliable_mask || mask.reliable_for_3d);
    $3("meshButton").disabled = !threeState.reliableMask;
    $3("surfaceTitle").textContent = mask.reliable_for_3d
      ? "Stable brain mask surface"
      : "Debug threshold mask preview - not final brain extraction";
    $3("maskSourceText").textContent = source;
    $3("maskText").textContent = threeState.reliableMask ? "reliable brain mask" : "threshold debug only";
    $3("maskRatioText").textContent = String(mask.mask_ratio ?? "-");
    $3("maskUniqueText").textContent = Array.isArray(mask.mask_unique_values) ? mask.mask_unique_values.join(", ") : "-";
    $3("maskStatusText").textContent = mask.mask_status || "-";
    $3("reliableMaskText").textContent = String(threeState.reliableMask);
    $3("brainMaskPathText").textContent = mask.mask_path || "-";
    $3("maskWarningText").textContent = threeState.reliableMask
      ? ""
      : "DEBUG ONLY: threshold mask, not brain extraction";
    $3("componentCountText").textContent = String(mask.component_count ?? "-");
    $3("largestComponentText").textContent = String(mask.largest_component_ratio ?? "-");
    $3("holeRatioText").textContent = String(mask.hole_ratio ?? "-");
    $3("edgeLeakageText").textContent = mask.edge_leakage === true ? "yes" : (mask.edge_leakage === false ? "no" : "-");
    $3("meshText").textContent = threeState.reliableMask
      ? "ready for brain-only mesh"
      : (mask.status_warning || "Reliable skull stripping is not available. Current mask is threshold debug only. Final 3D brain mesh is disabled.");
    if (!threeState.reliableMask) {
      setMeshFrameMessage("Brain mask is debug only. Final 3D disabled.", "warn");
    }
    $3("sliceImage").src = `/api/mask_overlay?t=${Date.now()}`;
  } finally {
    setBusy(false);
    syncFinalMeshButton();
  }
}

async function rebuildMask() {
  setBusy(true);
  try {
    const result = await apiGet("/api/rebuild_mask");
    threeState.reliableMask = false;
    setMeshFrameMessage("No mesh generated yet", "info");
    $3("surfaceTitle").textContent = "Debug threshold mask preview - not final brain extraction";
    $3("maskSourceText").textContent = result.mask_source || "none";
    $3("maskText").textContent = "cache cleared";
    $3("maskRatioText").textContent = "-";
    $3("maskUniqueText").textContent = "-";
    $3("maskStatusText").textContent = result.mask_status || "missing";
    $3("reliableMaskText").textContent = "false";
    $3("brainMaskPathText").textContent = "-";
    $3("brainOnlyPathText").textContent = "-";
    $3("meshPathText").textContent = "-";
    $3("debugMeshPathText").textContent = "-";
    $3("lastErrorText").textContent = "-";
    $3("componentCountText").textContent = "-";
    $3("largestComponentText").textContent = "-";
    $3("holeRatioText").textContent = "-";
    $3("edgeLeakageText").textContent = "-";
    $3("meshText").textContent = result.message || "Mask cache cleared.";
    $3("maskWarningText").textContent = "DEBUG ONLY: threshold mask, not brain extraction";
    $3("meshButton").disabled = true;
    await refreshThreeSlice();
  } finally {
    setBusy(false);
    syncFinalMeshButton();
  }
}

async function clearOutputs() {
  setBusy(true);
  try {
    const result = await apiGet("/api/clear_outputs");
    threeState.reliableMask = false;
    setMeshFrameMessage("No mesh generated yet", "info");
    $3("surfaceTitle").textContent = "Debug threshold mask preview - not final brain extraction";
    $3("maskSourceText").textContent = result.mask_source || "none";
    $3("maskText").textContent = "outputs cleared";
    $3("maskStatusText").textContent = result.mask_status || "missing";
    $3("reliableMaskText").textContent = "false";
    $3("brainMaskPathText").textContent = "-";
    $3("brainOnlyPathText").textContent = "-";
    $3("meshPathText").textContent = "-";
    $3("debugMeshPathText").textContent = "-";
    $3("lastErrorText").textContent = "-";
    $3("meshText").textContent = result.message || "Outputs cleared.";
    $3("maskWarningText").textContent = "DEBUG ONLY: threshold mask, not brain extraction";
    $3("meshButton").disabled = true;
    await refreshThreeSlice();
  } finally {
    setBusy(false);
    syncFinalMeshButton();
  }
}

async function runHdbet() {
  setBusy(true);
  try {
    $3("meshText").textContent = "running HD-BET";
    setMeshFrameMessage("No mesh generated yet", "info");
    const result = await apiGet("/api/run_hdbet");
    threeState.reliableMask = Boolean(result.reliable_mask);
    $3("hdbetInstalledText").textContent = String(Boolean(result.hdbet_installed));
    $3("maskSourceText").textContent = result.mask_source || "none";
    $3("maskStatusText").textContent = result.mask_status || "-";
    $3("reliableMaskText").textContent = String(threeState.reliableMask);
    $3("brainMaskPathText").textContent = result.brain_mask_path || "-";
    $3("brainOnlyPathText").textContent = result.brain_only_path || "-";
    $3("meshPathText").textContent = result.mesh_path || "-";
    $3("lastErrorText").textContent = result.last_error || result.message || "-";
    $3("surfaceTitle").textContent = threeState.reliableMask
      ? "Stable brain mask surface"
      : "Debug threshold mask preview - not final brain extraction";
    $3("maskWarningText").textContent = threeState.reliableMask
      ? ""
      : "DEBUG ONLY: threshold mask, not brain extraction";
    $3("meshButton").disabled = !threeState.reliableMask;
    $3("meshText").textContent = result.ok
      ? "HD-BET brain mask ready; build final 3D mesh enabled"
      : (result.message || "HD-BET failed; final 3D disabled");
    if (!threeState.reliableMask) {
      setMeshFrameMessage("Brain mask is debug only. Final 3D disabled.", "warn");
    }
    await refreshThreeSlice();
  } finally {
    setBusy(false);
    syncFinalMeshButton();
  }
}

async function generateDebugMesh() {
  setBusy(true);
  try {
    const { sigma, smooth, downsample } = meshParams();
    setMeshFrameMessage("Building 3D mesh...", "info");
    const meta = await apiGet(`/api/build-debug-mesh?sigma=${sigma}&smooth=${smooth}&downsample=${downsample}&step=1`);
    if (meta.ok === false) {
      const message = meta.message || "Debug mesh generation failed";
      $3("meshText").textContent = message;
      $3("lastErrorText").textContent = message;
      setMeshFrameMessage(`Mesh generation failed: ${message}`, "error");
      return;
    }
    $3("meshText").textContent = "DEBUG ONLY - not final brain extraction";
    $3("debugMeshPathText").textContent = meta.mesh_path || meta.output_path || "-";
    $3("maskWarningText").textContent = "DEBUG ONLY - not final brain extraction";
    loadDebugMeshPreview();
  } finally {
    setBusy(false);
    syncFinalMeshButton();
  }
}

function updateRegionStatus(regionStatus) {
  threeState.regions = Array.isArray(regionStatus.regions) ? regionStatus.regions : [];
  $3("synthsegAvailableText").textContent = String(Boolean(regionStatus.synthseg_available));
  $3("fastsurferAvailableText").textContent = String(Boolean(regionStatus.fastsurfer_available));
  $3("regionLabelmapText").textContent = regionStatus.labelmap_path || "-";
  $3("regionStatusText").textContent = regionStatus.status || "missing";
  $3("regionCsvPathText").textContent = regionStatus.volumes_csv_path || "-";
  const warning = regionStatus.disabled_warning || regionStatus.message || "";
  $3("regionWarningText").textContent = warning || "Region label map ready.";
  updateSelectedRegionVolume();
}

function updateSelectedRegionVolume() {
  const regionName = $3("regionSelect").value;
  const row = threeState.regions.find((item) => item.region_name === regionName);
  $3("regionVolumeText").textContent = row ? `${row.volume_ml} ml (${row.voxel_count} voxels)` : "-";
}

async function refreshRegionStatus() {
  const status = await apiGet("/api/regions/status");
  updateRegionStatus(status);
}

async function runRegionSegmentation() {
  setBusy(true);
  try {
    setMeshFrameMessage("Running region segmentation...", "info");
    const result = await apiGet("/api/regions/run");
    updateRegionStatus(result.region_status || result);
    if (!result.ok) {
      const message = result.message || "Region segmentation failed";
      $3("lastErrorText").textContent = message;
      setMeshFrameMessage(message, "warn");
      return;
    }
    $3("regionStatusText").textContent = "valid";
    await refreshThreeSlice();
  } finally {
    setBusy(false);
    syncFinalMeshButton();
  }
}

async function loadRegionLabelmap() {
  setBusy(true);
  try {
    const result = await apiGet("/api/regions/load");
    updateRegionStatus(result);
    if (!result.ok) {
      const message = result.message || "Label map not found";
      $3("lastErrorText").textContent = message;
      setMeshFrameMessage(message, "warn");
      return;
    }
    await refreshThreeSlice();
  } finally {
    setBusy(false);
    syncFinalMeshButton();
  }
}

async function buildSelectedRegionMesh() {
  setBusy(true);
  try {
    const region = encodeURIComponent($3("regionSelect").value);
    setMeshFrameMessage("Building 3D mesh...", "info");
    const result = await apiGet(`/api/regions/build-mesh?region=${region}`);
    if (!result.ok) {
      const message = result.message || "Mesh generation failed";
      $3("lastErrorText").textContent = message;
      setMeshFrameMessage(`Mesh generation failed: ${message}`, "error");
      return;
    }
    $3("regionMeshPathText").textContent = result.mesh_path || "-";
    $3("meshText").textContent = `${result.region_name}: ${result.vertices} vertices / ${result.faces} faces`;
    loadRegionMeshPreview();
    await refreshRegionStatus();
  } finally {
    setBusy(false);
    syncFinalMeshButton();
  }
}

async function buildAllRegionMeshes() {
  setBusy(true);
  try {
    setMeshFrameMessage("Building 3D mesh...", "info");
    const result = await apiGet("/api/regions/build-all-meshes");
    if (!result.ok) {
      const message = result.message || "Region mesh generation failed";
      $3("lastErrorText").textContent = message;
      setMeshFrameMessage(`Mesh generation failed: ${message}`, "error");
      return;
    }
    $3("regionCsvPathText").textContent = result.volumes_csv_path || "-";
    await buildSelectedRegionMesh();
  } finally {
    setBusy(false);
    syncFinalMeshButton();
  }
}

async function exportRegionCsv() {
  setBusy(true);
  try {
    const result = await apiGet("/api/regions/export-volumes");
    if (!result.ok) {
      $3("lastErrorText").textContent = result.message || "CSV export failed";
      return;
    }
    $3("regionCsvPathText").textContent = result.csv_path || "-";
    updateRegionStatus({ regions: result.regions, volumes_csv_path: result.csv_path, status: "valid" });
  } finally {
    setBusy(false);
    syncFinalMeshButton();
  }
}

function meshParams() {
  return {
    sigma: encodeURIComponent($3("sigmaInput").value),
    smooth: encodeURIComponent($3("smoothInput").value),
    downsample: encodeURIComponent($3("downsampleInput").value),
  };
}

function meshStatusHtml(message, tone = "info") {
  const palette = {
    info: ["#f8fafc", "#0f172a", "#38bdf8"],
    warn: ["#fffbeb", "#713f12", "#f59e0b"],
    error: ["#fff1f2", "#7f1d1d", "#ef4444"],
    ok: ["#ecfdf5", "#064e3b", "#10b981"],
  }[tone] || ["#f8fafc", "#0f172a", "#38bdf8"];
  const safeMessage = String(message).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "\"": "&quot;",
    "'": "&#39;",
  }[char]));
  return `<!doctype html><html><body style="margin:0;min-height:100vh;display:grid;place-items:center;background:${palette[0]};font-family:system-ui,-apple-system,Segoe UI,sans-serif;color:${palette[1]}">
    <div style="width:min(520px,84%);border:1px solid rgba(15,23,42,.12);border-left:6px solid ${palette[2]};border-radius:8px;background:#fff;padding:22px 24px;box-shadow:0 18px 48px rgba(15,23,42,.10)">
      <strong style="display:block;font-size:18px;margin-bottom:8px">${safeMessage}</strong>
      <span style="font-size:13px;color:#64748b">AIDLC-MRI 3D Preview</span>
    </div>
  </body></html>`;
}

function setMeshFrameMessage(message, tone = "info") {
  const frame = $3("meshFrame");
  frame.removeAttribute("src");
  frame.srcdoc = meshStatusHtml(message, tone);
  $3("meshText").textContent = message;
}

function loadMeshPreview() {
  if (!threeState.reliableMask) {
    setMeshFrameMessage("Brain mask is debug only. Final 3D disabled.", "warn");
    return;
  }
  const { sigma, smooth, downsample } = meshParams();
  $3("meshText").textContent = "loading preview";
  $3("meshFrame").removeAttribute("srcdoc");
  $3("meshFrame").src = `/api/mesh_plot?sigma=${sigma}&smooth=${smooth}&downsample=${downsample}&step=1&t=${Date.now()}`;
}

function loadDebugMeshPreview() {
  const { sigma, smooth, downsample } = meshParams();
  $3("meshText").textContent = "DEBUG ONLY - not final brain extraction";
  $3("meshFrame").removeAttribute("srcdoc");
  $3("meshFrame").src = `/api/mesh_plot?debug=1&sigma=${sigma}&smooth=${smooth}&downsample=${downsample}&step=1&t=${Date.now()}`;
}

function loadRegionMeshPreview() {
  const region = encodeURIComponent($3("regionSelect").value);
  $3("meshFrame").removeAttribute("srcdoc");
  $3("meshFrame").src = `/api/regions/mesh_plot?region=${region}&smooth=2&downsample=1&t=${Date.now()}`;
}

function bindThreeControls() {
  $3("loadButton").addEventListener("click", loadThreeVolume);
  $3("maskButton").addEventListener("click", generateMask);
  $3("rebuildMaskButton").addEventListener("click", rebuildMask);
  $3("clearOutputsButton").addEventListener("click", clearOutputs);
  $3("runHdbetButton").addEventListener("click", runHdbet);
  $3("meshButton").addEventListener("click", generateMesh);
  $3("debugMeshButton").addEventListener("click", generateDebugMesh);
  $3("runRegionButton").addEventListener("click", runRegionSegmentation);
  $3("loadRegionButton").addEventListener("click", loadRegionLabelmap);
  $3("buildRegionMeshButton").addEventListener("click", buildSelectedRegionMesh);
  $3("buildAllRegionMeshesButton").addEventListener("click", buildAllRegionMeshes);
  $3("exportRegionCsvButton").addEventListener("click", exportRegionCsv);
  $3("regionOverlayToggle").addEventListener("change", refreshThreeSlice);
  $3("regionSelect").addEventListener("change", () => {
    updateSelectedRegionVolume();
    refreshThreeSlice();
  });
  $3("meshFrame").addEventListener("load", () => {
    if ($3("meshFrame").getAttribute("src")) {
      if ($3("meshText").textContent === "loading preview") {
        $3("meshText").textContent = threeState.meshPreviewText || "mask-based mesh preview available";
      }
    }
  });
  $3("planeSelect").addEventListener("change", refreshThreeSlice);
  $3("maskToggle").addEventListener("change", refreshThreeSlice);
  $3("sliceRange").addEventListener("input", () => {
    $3("sliceValueLabel").textContent = $3("sliceRange").value;
    refreshThreeSlice();
  });
}

async function bootThree() {
  bindThreeControls();
  setMeshFrameMessage("No mesh generated yet", "info");
  setBusy(true);
  try {
    await loadThreeSeriesList();
    await loadThreeVolume();
  } finally {
    setBusy(false);
    syncFinalMeshButton();
  }
}

bootThree().catch(showPageError);
