const threeState = {
  status: null,
  series: [],
  meshPreviewText: "",
  reliableMask: false,
  regions: [],
  metadata: null,
  sliceReady: false,
  sliceObjectUrl: "",
  maskType: "none",
  meshStatus: "none",
  debugMeshFallbackTimer: null,
};

const $3 = (id) => document.getElementById(id);

function syncFinalMeshButton() {
  $3("meshButton").disabled = !threeState.reliableMask;
  const canBuildDebugPreview = Boolean(threeState.metadata?.volume_loaded) && threeState.maskType === "debug";
  $3("debugMeshButton").disabled = !canBuildDebugPreview;
}

function updateMeshStatePanel(meshStatus = {}) {
  const status = threeState.status || {};
  const maskType = meshStatus.mask_type || threeState.maskType || "none";
  const meshState = meshStatus.mesh_status || threeState.meshStatus || "none";
  const glbUrl = meshStatus.glb_url || meshStatus.mesh_url || meshStatus.debug_mesh_url || "";
  $3("volumeLoadedText").textContent = String(Boolean(meshStatus.volume_loaded ?? status.volume_loaded));
  $3("maskTypeText").textContent = maskType;
  $3("maskVoxelCountText").textContent = String(meshStatus.voxel_count ?? meshStatus.mask_voxel_count ?? meshStatus.mask_sum ?? status.mask_sum ?? 0);
  $3("meshApiStatusText").textContent = meshStatus.mesh_api_status || meshStatus.mesh_status || "none";
  $3("meshStatusText").textContent = meshState;
  $3("activeMeshPathText").textContent = meshStatus.debug_mesh_path || meshStatus.mesh_path || status.final_mesh_path || status.mesh_path || "-";
  $3("glbUrlText").textContent = glbUrl || "-";
  $3("meshFileExistsText").textContent = String(Boolean(meshStatus.file_exists));
  $3("meshFileSizeText").textContent = String(meshStatus.file_size ?? 0);
  $3("meshVertexCountText").textContent = String(meshStatus.vertex_count ?? meshStatus.vertices ?? "-");
  $3("meshFaceCountText").textContent = String(meshStatus.face_count ?? meshStatus.faces ?? "-");
  $3("meshLastErrorText").textContent = meshStatus.last_error || status.last_error || "-";
}

function debugPreviewWarning() {
  return "Debug mask only. Not for diagnosis. Preview mesh only. Final brain-only 3D requires SynthStrip or HD-BET.";
}

window.addEventListener("message", (event) => {
  if (event.data?.type === "debugMeshReady" && threeState.debugMeshFallbackTimer) {
    window.clearTimeout(threeState.debugMeshFallbackTimer);
    threeState.debugMeshFallbackTimer = null;
  }
});

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
  const metadata = await apiGet("/api/mri/metadata");
  const meshStatus = await apiGet("/api/mesh-status");
  threeState.status = status;
  threeState.metadata = metadata;
  threeState.reliableMask = Boolean(status.reliable_mask);
  threeState.maskType = meshStatus.mask_type || (threeState.reliableMask ? "final" : (Number(status.mask_sum || 0) > 0 ? "debug" : "none"));
  threeState.meshStatus = meshStatus.mesh_status || "none";
  $3("sourceText").textContent = metadata.source || status.source || "-";
  $3("shapeText").textContent = formatShape(metadata.shape || status.shape);
  $3("spacingText").textContent = formatSpacing(metadata.spacing || status.spacing);
  $3("sliceCountText").textContent = String(status.slice_count || "-");
  $3("seriesText").textContent = metadata.series_name || metadata.series || status.info?.SeriesDescription || status.source_label || "-";
  $3("hdbetInstalledText").textContent = String(Boolean(status.hdbet_installed));
  $3("synthstripAvailableText").textContent = String(Boolean(status.synthstrip_available));
  $3("maskSourceText").textContent = metadata.mask_source || status.mask_source || "none";
  $3("maskStatusText").textContent = metadata.mask_status || status.mask_status || "missing";
  $3("reliableMaskText").textContent = String(threeState.reliableMask);
  $3("maskShapeText").textContent = formatShape(status.mask_shape);
  $3("maskSumText").textContent = String(status.mask_sum ?? "-");
  $3("maskRatioText").textContent = String(metadata.mask_ratio ?? status.mask_ratio ?? "-");
  $3("maskUniqueText").textContent = Array.isArray(metadata.mask_unique_values) ? metadata.mask_unique_values.join(", ") : "-";
  $3("inputNiftiPathText").textContent = status.input_nifti_path || "-";
  $3("brainMaskPathText").textContent = status.brain_mask_path || "-";
  $3("brainOnlyPathText").textContent = status.brain_only_path || "-";
  $3("meshPathText").textContent = status.final_mesh_path || status.mesh_path || "-";
  $3("debugMeshPathText").textContent = status.debug_mesh_path || "-";
  $3("lastErrorText").textContent = status.last_error || "-";
  updateRegionStatus(status.region_segmentation || {});
  $3("meshButton").disabled = !threeState.reliableMask;
  updateMeshStatePanel(meshStatus);
  $3("surfaceTitle").textContent = threeState.reliableMask
    ? "Stable brain mask surface"
    : "Debug brain mask preview";
  $3("maskWarningText").textContent = threeState.reliableMask
    ? ""
    : debugPreviewWarning();
  $3("meshText").textContent = meshStatus.status || (status.mesh_available ? "3D mesh loaded" : "No mesh generated yet");
  if (!metadata.volume_loaded) {
    setMeshFrameMessage("volume not loaded", "warn");
  } else if (meshStatus.mesh_available) {
    loadMeshPreview();
  } else if (meshStatus.debug_mesh_available && meshStatus.file_exists && !threeState.reliableMask) {
    loadDebugMeshPreview(meshStatus.debug_mesh_url || "/static/meshes/debug_brain_preview.glb");
  } else if (threeState.maskType === "debug") {
    setMeshFrameMessage("Preview mesh not generated yet. Click Generate Preview 3D.", "warn");
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
  const overlay = $3("maskToggle").value === "1";
  const regionOverlay = $3("regionOverlayToggle").value;
  threeState.sliceReady = false;
  if (regionOverlay !== "0") {
    const region = encodeURIComponent($3("regionSelect").value);
    const mode = regionOverlay === "all" ? "all" : "selected";
    await loadThreeSliceImage(
      `/api/regions/overlay?plane=${encodeURIComponent(plane)}&index=${index}&region=${region}&mode=${mode}&t=${Date.now()}`,
      { plane, index, overlay: regionOverlay, series: $3("seriesText").textContent }
    );
  } else {
    const url = `/api/mri/slice?plane=${encodeURIComponent(plane)}&index=${index}&overlay=${overlay ? "true" : "false"}&t=${Date.now()}`;
    console.log("[MRI 3D] slice preview request URL:", url);
    await loadThreeSliceImage(url, { plane, index, overlay, series: $3("seriesText").textContent });
  }
}

async function loadThreeSliceImage(url, context) {
  console.log("[MRI 3D] slice preview request URL:", url);
  hideThreeSliceError();
  try {
    const response = await fetch(url, { cache: "no-store" });
    const contentType = response.headers.get("content-type") || "";
    if (!response.ok || !contentType.includes("image/png")) {
      const message = await response.text();
      showThreeSliceError({
        ...context,
        url,
        status: `${response.status} ${response.statusText}`,
        message: message || `Unexpected content type: ${contentType || "empty"}`,
      });
      return;
    }
    const blob = await response.blob();
    if (threeState.sliceObjectUrl) URL.revokeObjectURL(threeState.sliceObjectUrl);
    threeState.sliceObjectUrl = URL.createObjectURL(blob);
    $3("sliceImage").onerror = () => showThreeSliceError({
      ...context,
      url,
      status: "image decode failed",
      message: "Browser could not decode the PNG response.",
    });
    $3("sliceImage").onload = () => {
      threeState.sliceReady = true;
      hideThreeSliceError();
      if (!threeState.reliableMask && $3("meshText").textContent === "No mesh generated yet") {
        $3("meshText").textContent = "slice preview ready; mask missing";
      }
    };
    $3("sliceImage").src = threeState.sliceObjectUrl;
  } catch (error) {
    showThreeSliceError({
      ...context,
      url,
      status: "network error",
      message: error instanceof Error ? error.message : String(error),
    });
  }
}

function hideThreeSliceError() {
  const panel = $3("sliceErrorPanel");
  if (panel) panel.classList.add("hidden");
  $3("sliceImage").style.visibility = "visible";
}

function showThreeSliceError(details) {
  const metadata = threeState.metadata || {};
  $3("sliceErrorUrl").textContent = details.url || "-";
  $3("sliceErrorStatus").textContent = details.status || "-";
  $3("sliceErrorSeries").textContent = details.series || metadata.series_name || "-";
  $3("sliceErrorPlane").textContent = details.plane || "-";
  $3("sliceErrorIndex").textContent = String(details.index ?? "-");
  $3("sliceErrorOverlay").textContent = String(details.overlay ?? "-");
  $3("sliceErrorLoaded").textContent = String(Boolean(metadata.volume_loaded ?? threeState.status?.volume_loaded));
  $3("sliceErrorMaskExists").textContent = String(Boolean(metadata.mask_exists));
  $3("sliceErrorMessage").textContent = details.message || "-";
  $3("sliceImage").removeAttribute("src");
  $3("sliceImage").style.visibility = "hidden";
  $3("sliceErrorPanel").classList.remove("hidden");
  threeState.sliceReady = false;
}

async function generateMesh() {
  setBusy(true);
  try {
    if (!threeState.reliableMask) {
      const message = "No valid brain mask. Generate/check brain mask first.";
      $3("meshText").textContent = message;
      $3("lastErrorText").textContent = message;
      setMeshFrameMessage(message, "warn");
      return;
    }
    const { sigma, smooth, downsample } = meshParams();
    setMeshFrameMessage("Building 3D mesh...", "info");
    $3("meshStatusText").textContent = "generating";
    const meta = await apiGet(`/api/build-mesh?sigma=${sigma}&smooth=${smooth}&downsample=${downsample}&step=1`);
    if (meta.ok === false) {
      threeState.reliableMask = false;
      const message = meta.message || meta.warning || meta.exception || "Mesh generation failed";
      $3("meshText").textContent = message;
      $3("lastErrorText").textContent = message;
      setMeshFrameMessage(`Mesh generation failed: ${message}`, "error");
      $3("meshStatusText").textContent = "failed";
      return;
    }
    threeState.meshPreviewText = `3D mesh loaded: ${meta.vertices} vertices / ${meta.faces} faces`;
    $3("meshText").textContent = threeState.meshPreviewText;
    $3("meshPathText").textContent = meta.mesh_path || "-";
    $3("activeMeshPathText").textContent = meta.static_mesh_path || meta.mesh_path || "-";
    $3("meshStatusText").textContent = "ready";
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
      : "Debug brain mask preview";
    $3("maskSourceText").textContent = source;
    $3("maskText").textContent = threeState.reliableMask ? "reliable brain mask" : "threshold debug only";
    $3("maskRatioText").textContent = String(mask.mask_ratio ?? "-");
    $3("maskUniqueText").textContent = Array.isArray(mask.mask_unique_values) ? mask.mask_unique_values.join(", ") : "-";
    $3("maskStatusText").textContent = mask.mask_status || "-";
    $3("reliableMaskText").textContent = String(threeState.reliableMask);
    $3("brainMaskPathText").textContent = mask.mask_path || "-";
    $3("maskWarningText").textContent = threeState.reliableMask
      ? ""
      : debugPreviewWarning();
    $3("componentCountText").textContent = String(mask.component_count ?? "-");
    $3("largestComponentText").textContent = String(mask.largest_component_ratio ?? "-");
    $3("holeRatioText").textContent = String(mask.hole_ratio ?? "-");
    $3("edgeLeakageText").textContent = mask.edge_leakage === true ? "yes" : (mask.edge_leakage === false ? "no" : "-");
    $3("meshText").textContent = threeState.reliableMask
      ? "mask ready; final 3D mesh enabled"
      : "Debug brain mask detected. Preview 3D mesh can be generated, but final medical brain-only 3D is disabled.";
    if (!threeState.reliableMask) {
      setMeshFrameMessage("Debug brain mask detected. Preview 3D mesh can be generated, but final medical brain-only 3D is disabled.", "warn");
    }
    await refreshThreeStatus();
    await refreshThreeSlice();
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
    $3("surfaceTitle").textContent = "Debug brain mask preview";
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
    $3("maskWarningText").textContent = debugPreviewWarning();
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
    $3("surfaceTitle").textContent = "Debug brain mask preview";
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
    $3("maskWarningText").textContent = debugPreviewWarning();
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
      : "Debug brain mask preview";
    $3("maskWarningText").textContent = threeState.reliableMask
      ? ""
      : debugPreviewWarning();
    $3("meshButton").disabled = !threeState.reliableMask;
    $3("meshText").textContent = result.ok
      ? "HD-BET brain mask ready; build final 3D mesh enabled"
      : (result.message || "HD-BET failed; final 3D disabled");
    if (!threeState.reliableMask) {
      setMeshFrameMessage("Debug brain mask detected. Preview 3D mesh can be generated, but final medical brain-only 3D is disabled.", "warn");
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
    setMeshFrameMessage("Generating preview mesh from debug mask...", "info");
    $3("meshStatusText").textContent = "generating";
    const meta = await apiGet(`/api/mri/mesh/debug-preview?sigma=${sigma}&smooth=${smooth}&downsample=${Math.max(4, Number(downsample) || 4)}&step=1`);
    if (meta.ok === false) {
      const message = [meta.message || "Debug preview mesh generation failed", meta.traceback || ""].filter(Boolean).join("\n");
      $3("meshText").textContent = message;
      $3("lastErrorText").textContent = message;
      $3("meshLastErrorText").textContent = message;
      $3("meshStatusText").textContent = "failed";
      $3("maskVoxelCountText").textContent = String(meta.mask_voxel_count ?? "-");
      setMeshFrameMessage(`Mesh generation failed: ${message}`, "error");
      return;
    }
    $3("meshText").textContent = "Preview mesh ready. Debug mask only / Not for diagnosis.";
    $3("debugMeshPathText").textContent = meta.mesh_path || "-";
    $3("activeMeshPathText").textContent = meta.mesh_path || "-";
    $3("meshStatusText").textContent = "ready";
    $3("meshApiStatusText").textContent = meta.mesh_status || "ready";
    $3("glbUrlText").textContent = meta.mesh_url || meta.mesh_path || "-";
    $3("meshFileExistsText").textContent = String(Boolean(meta.file_exists ?? true));
    $3("meshFileSizeText").textContent = String(meta.file_size ?? "-");
    $3("meshVertexCountText").textContent = String(meta.vertex_count ?? meta.vertices ?? "-");
    $3("meshFaceCountText").textContent = String(meta.face_count ?? meta.faces ?? "-");
    $3("maskTypeText").textContent = "debug";
    $3("maskVoxelCountText").textContent = String(meta.voxel_count ?? meta.mask_voxel_count ?? "-");
    $3("maskWarningText").textContent = meta.warning || debugPreviewWarning();
    loadDebugMeshPreview(meta.mesh_url || meta.mesh_path || "/static/meshes/debug_brain_preview.glb");
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
    setMeshFrameMessage("Debug brain mask detected. Preview 3D mesh can be generated, but final medical brain-only 3D is disabled.", "warn");
    return;
  }
  const { sigma, smooth, downsample } = meshParams();
  $3("meshText").textContent = "loading preview";
  $3("meshFrame").removeAttribute("srcdoc");
  $3("meshFrame").src = `/api/mesh_plot?sigma=${sigma}&smooth=${smooth}&downsample=${downsample}&step=1&t=${Date.now()}`;
}

function loadDebugMeshPreview(meshUrl = "/static/meshes/debug_brain_preview.glb") {
  if (threeState.debugMeshFallbackTimer) {
    window.clearTimeout(threeState.debugMeshFallbackTimer);
  }
  threeState.meshStatus = "ready";
  console.log("[3D] loading GLB:", meshUrl);
  $3("meshText").textContent = "Preview mesh only - not final brain extraction";
  $3("meshStatusText").textContent = "ready";
  $3("activeMeshPathText").textContent = meshUrl;
  $3("meshLastErrorText").textContent = "-";
  $3("meshFrame").removeAttribute("srcdoc");
  $3("meshFrame").src = `/api/threejs_viewer?model=${encodeURIComponent(meshUrl)}&title=${encodeURIComponent("Debug brain preview mesh")}&warning=${encodeURIComponent(debugPreviewWarning())}&t=${Date.now()}`;
  threeState.debugMeshFallbackTimer = window.setTimeout(() => {
    const frame = $3("meshFrame");
    if (frame?.src.includes("/api/threejs_viewer")) {
      $3("meshText").textContent = "Preview mesh surface fallback - debug mask only / not for diagnosis";
    }
  }, 10000);
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
  $3("maskToggle").value = "1";
  $3("regionOverlayToggle").value = "0";
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
