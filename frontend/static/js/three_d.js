const threeState = {
  status: null,
  series: [],
  meshPreviewText: "",
  reliableMask: false,
};

const $3 = (id) => document.getElementById(id);

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
  threeState.status = status;
  threeState.reliableMask = Boolean(status.reliable_mask);
  $3("sourceText").textContent = status.source || "-";
  $3("shapeText").textContent = formatShape(status.shape);
  $3("spacingText").textContent = formatSpacing(status.spacing);
  $3("seriesText").textContent = status.info?.SeriesDescription || status.source_label || "-";
  $3("hdbetInstalledText").textContent = String(Boolean(status.hdbet_installed));
  $3("maskSourceText").textContent = status.mask_source || "none";
  $3("maskStatusText").textContent = status.mask_status || "missing";
  $3("reliableMaskText").textContent = String(threeState.reliableMask);
  $3("brainMaskPathText").textContent = status.brain_mask_path || "-";
  $3("meshPathText").textContent = status.mesh_path || "-";
  $3("lastErrorText").textContent = status.last_error || "-";
  $3("meshButton").disabled = !threeState.reliableMask;
  $3("surfaceTitle").textContent = threeState.reliableMask
    ? "Stable brain mask surface"
    : "Debug threshold mask preview - not final brain extraction";
  $3("maskWarningText").textContent = threeState.reliableMask
    ? ""
    : "DEBUG ONLY: threshold mask, not brain extraction";
  $3("meshText").textContent = status.mesh_available
    ? "brain-only mesh available"
    : "Reliable skull stripping is not available. Current mask is debug only. Final 3D brain mesh is disabled.";
  if (status.disclaimer) $3("disclaimer").textContent = status.disclaimer;
  updateThreeSliceLimit();
}

async function loadThreeVolume() {
  setBusy(true);
  try {
    const key = encodeURIComponent($3("seriesSelect").value);
    await apiGet(`/api/load?series_key=${key}`);
    await refreshThreeStatus();
    await refreshThreeSlice();
    $3("meshFrame").removeAttribute("src");
    $3("maskText").textContent = "not checked";
    $3("maskRatioText").textContent = "-";
    $3("maskUniqueText").textContent = "-";
    $3("componentCountText").textContent = "-";
    $3("largestComponentText").textContent = "-";
    $3("holeRatioText").textContent = "-";
    $3("edgeLeakageText").textContent = "-";
  } finally {
    setBusy(false);
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
  $3("sliceImage").src = `/api/slice?plane=${encodeURIComponent(plane)}&index=${index}&mask=${mask}&t=${Date.now()}`;
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
      $3("meshFrame").removeAttribute("src");
      if (!threeState.reliableMask) return;
    }
    const { sigma, smooth, downsample } = meshParams();
    const meta = await apiGet(`/api/mesh?sigma=${sigma}&smooth=${smooth}&downsample=${downsample}&step=1`);
    if (meta.ok === false) {
      threeState.reliableMask = false;
      $3("meshText").textContent = meta.warning || meta.message || "Final 3D brain mesh is disabled.";
      $3("meshFrame").removeAttribute("src");
      return;
    }
    const mode = meta.reliable_for_3d ? "brain-only" : "debug only / not final brain mask";
    threeState.meshPreviewText = `${mode}: ${meta.vertices} vertices / ${meta.faces} faces`;
    $3("meshText").textContent = threeState.meshPreviewText;
    $3("meshPathText").textContent = meta.mesh_path || "-";
    loadMeshPreview();
  } finally {
    setBusy(false);
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
    $3("sliceImage").src = `/api/mask_overlay?t=${Date.now()}`;
  } finally {
    setBusy(false);
  }
}

async function rebuildMask() {
  setBusy(true);
  try {
    const result = await apiGet("/api/rebuild_mask");
    threeState.reliableMask = false;
    $3("meshFrame").removeAttribute("src");
    $3("surfaceTitle").textContent = "Debug threshold mask preview - not final brain extraction";
    $3("maskSourceText").textContent = result.mask_source || "none";
    $3("maskText").textContent = "cache cleared";
    $3("maskRatioText").textContent = "-";
    $3("maskUniqueText").textContent = "-";
    $3("maskStatusText").textContent = result.mask_status || "missing";
    $3("reliableMaskText").textContent = "false";
    $3("brainMaskPathText").textContent = "-";
    $3("meshPathText").textContent = "-";
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
  }
}

async function clearOutputs() {
  setBusy(true);
  try {
    const result = await apiGet("/api/clear_outputs");
    threeState.reliableMask = false;
    $3("meshFrame").removeAttribute("src");
    $3("surfaceTitle").textContent = "Debug threshold mask preview - not final brain extraction";
    $3("maskSourceText").textContent = result.mask_source || "none";
    $3("maskText").textContent = "outputs cleared";
    $3("maskStatusText").textContent = result.mask_status || "missing";
    $3("reliableMaskText").textContent = "false";
    $3("brainMaskPathText").textContent = "-";
    $3("meshPathText").textContent = "-";
    $3("lastErrorText").textContent = "-";
    $3("meshText").textContent = result.message || "Outputs cleared.";
    $3("maskWarningText").textContent = "DEBUG ONLY: threshold mask, not brain extraction";
    $3("meshButton").disabled = true;
    await refreshThreeSlice();
  } finally {
    setBusy(false);
  }
}

async function runHdbet() {
  setBusy(true);
  try {
    $3("meshText").textContent = "running HD-BET";
    const result = await apiGet("/api/run_hdbet");
    threeState.reliableMask = Boolean(result.reliable_mask);
    $3("hdbetInstalledText").textContent = String(Boolean(result.hdbet_installed));
    $3("maskSourceText").textContent = result.mask_source || "none";
    $3("maskStatusText").textContent = result.mask_status || "-";
    $3("reliableMaskText").textContent = String(threeState.reliableMask);
    $3("brainMaskPathText").textContent = result.brain_mask_path || "-";
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
    await refreshThreeSlice();
  } finally {
    setBusy(false);
  }
}

function meshParams() {
  return {
    sigma: encodeURIComponent($3("sigmaInput").value),
    smooth: encodeURIComponent($3("smoothInput").value),
    downsample: encodeURIComponent($3("downsampleInput").value),
  };
}

function loadMeshPreview() {
  if (!threeState.reliableMask) {
    $3("meshFrame").removeAttribute("src");
    $3("meshText").textContent = "Reliable skull stripping is not available. Current mask is threshold debug only. Final 3D brain mesh is disabled.";
    return;
  }
  const { sigma, smooth, downsample } = meshParams();
  $3("meshText").textContent = "loading preview";
  $3("meshFrame").src = `/api/mesh_plot?sigma=${sigma}&smooth=${smooth}&downsample=${downsample}&step=1&t=${Date.now()}`;
}

function bindThreeControls() {
  $3("loadButton").addEventListener("click", loadThreeVolume);
  $3("maskButton").addEventListener("click", generateMask);
  $3("rebuildMaskButton").addEventListener("click", rebuildMask);
  $3("clearOutputsButton").addEventListener("click", clearOutputs);
  $3("runHdbetButton").addEventListener("click", runHdbet);
  $3("meshButton").addEventListener("click", generateMesh);
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
  setBusy(true);
  try {
    await loadThreeSeriesList();
    await loadThreeVolume();
  } finally {
    setBusy(false);
  }
}

bootThree().catch(showPageError);
