const viewerState = {
  status: null,
  metadata: null,
  series: [],
  sliceLoaded: false,
  activeObjectUrl: "",
};

const API_BASE = "";
const $ = (id) => document.getElementById(id);

async function loadSeriesList() {
  const data = await apiGet("/api/series");
  viewerState.series = data.series || [];
  $("seriesSelect").innerHTML = "";
  for (const item of viewerState.series) {
    const option = document.createElement("option");
    option.value = item.key;
    option.textContent = `${item.description || "Series"} | ${item.file_count} files | ${item.shape || ""}`;
    $("seriesSelect").appendChild(option);
  }
}

async function refreshStatus() {
  const status = await apiGet("/api/status");
  const metadata = await apiGet("/api/mri/metadata");
  viewerState.status = status;
  viewerState.metadata = metadata;
  $("sourceText").textContent = metadata.source || status.source || "-";
  $("shapeText").textContent = formatShape(metadata.shape || status.shape);
  $("spacingText").textContent = formatSpacing(metadata.spacing || status.spacing);
  $("seriesText").textContent = metadata.series || status.info?.SeriesDescription || status.source_label || "-";
  $("maskSourceText").textContent = metadata.mask_source || status.mask_source || "none";
  $("maskRatioText").textContent = String(metadata.mask_ratio ?? status.mask_ratio ?? "-");
  $("maskUniqueText").textContent = Array.isArray(metadata.mask_unique_values)
    ? metadata.mask_unique_values.join(", ")
    : "-";
  $("maskStatusText").textContent = metadata.mask_status || status.mask_status || "missing";
  const region = status.region_segmentation || {};
  $("regionStatusText").textContent = region.status || "missing";
  $("regionLabelmapText").textContent = region.labelmap_path || "-";
  if ($("disclaimer") && status.disclaimer) $("disclaimer").textContent = status.disclaimer;
  updateSliceLimit();
}

async function loadVolume() {
  setBusy(true);
  try {
    const key = encodeURIComponent($("seriesSelect").value);
    await apiGet(`/api/load?series_key=${key}`);
    resetMaskStatus();
    await refreshStatus();
    await refreshSlice();
  } finally {
    setBusy(false);
  }
}

function updateSliceLimit() {
  const shape = viewerState.status?.shape;
  if (!shape) return;
  const plane = $("planeSelect").value;
  const max = Math.max(0, planeLength(shape, plane) - 1);
  $("sliceRange").max = String(max);
  $("sliceValue").max = String(max);
  const current = Math.min(Number($("sliceRange").value), max);
  $("sliceRange").value = String(current);
  $("sliceValue").value = String(current);
}

async function refreshSlice() {
  updateSliceLimit();
  const plane = $("planeSelect").value;
  const index = Number($("sliceRange").value);
  const mask = $("maskToggle").value;
  const overlayType = $("overlayTypeSelect").value;
  const region = $("regionSelect").value;
  $("sliceTitle").textContent = `${plane.charAt(0).toUpperCase()}${plane.slice(1)} slice`;
  $("open3dLink").classList.add("disabled");
  $("open3dLink").setAttribute("aria-disabled", "true");
  viewerState.sliceLoaded = false;

  const params = new URLSearchParams({
    plane,
    index: String(index),
    region,
    t: String(Date.now()),
  });
  if (overlayType === "region_selected" || overlayType === "region_all") {
    const mode = overlayType === "region_all" ? "all" : "selected";
    params.set("mode", mode);
    await loadSliceImage(`${API_BASE}/api/regions/overlay?${params.toString()}`, { plane, index });
  } else {
    params.set("mask", mask);
    await loadSliceImage(`${API_BASE}/api/mri/slice?${params.toString()}`, { plane, index });
  }
}

async function loadSliceImage(url, context) {
  console.log("[MRI viewer] slice image request URL:", url);
  hideSliceError();
  try {
    const response = await fetch(url, { cache: "no-store" });
    const contentType = response.headers.get("content-type") || "";
    if (!response.ok || !contentType.includes("image/png")) {
      const message = await response.text();
      showSliceError({
        url,
        status: `${response.status} ${response.statusText}`,
        message: message || `Unexpected content type: ${contentType || "empty"}`,
        plane: context.plane,
        index: context.index,
      });
      return;
    }
    const blob = await response.blob();
    if (viewerState.activeObjectUrl) URL.revokeObjectURL(viewerState.activeObjectUrl);
    viewerState.activeObjectUrl = URL.createObjectURL(blob);
    $("sliceImage").onerror = () => {
      showSliceError({
        url,
        status: "image decode failed",
        message: "Browser could not decode the PNG response.",
        plane: context.plane,
        index: context.index,
      });
    };
    $("sliceImage").onload = () => {
      viewerState.sliceLoaded = true;
      $("open3dLink").classList.remove("disabled");
      $("open3dLink").setAttribute("aria-disabled", "false");
      hideSliceError();
    };
    $("sliceImage").src = viewerState.activeObjectUrl;
  } catch (error) {
    showSliceError({
      url,
      status: "network error",
      message: error instanceof Error ? error.message : String(error),
      plane: context.plane,
      index: context.index,
    });
  }
}

function hideSliceError() {
  $("sliceErrorPanel").classList.add("hidden");
  $("sliceImage").style.visibility = "visible";
}

function showSliceError(details) {
  const loaded = Boolean(viewerState.metadata?.volume_loaded ?? viewerState.status?.volume_loaded);
  $("sliceErrorUrl").textContent = details.url || "-";
  $("sliceErrorStatus").textContent = details.status || "-";
  $("sliceErrorMessage").textContent = details.message || "-";
  $("sliceErrorPlane").textContent = details.plane || "-";
  $("sliceErrorIndex").textContent = String(details.index ?? "-");
  $("sliceErrorLoaded").textContent = String(loaded);
  $("sliceImage").removeAttribute("src");
  $("sliceImage").style.visibility = "hidden";
  $("sliceErrorPanel").classList.remove("hidden");
  $("open3dLink").classList.add("disabled");
  $("open3dLink").setAttribute("aria-disabled", "true");
}

function resetMaskStatus() {
  $("maskSourceText").textContent = "-";
  $("maskText").textContent = "not checked";
  $("maskRatioText").textContent = "-";
  $("maskUniqueText").textContent = "-";
  $("maskStatusText").textContent = "-";
  $("componentCountText").textContent = "-";
  $("largestComponentText").textContent = "-";
  $("holeRatioText").textContent = "-";
  $("edgeLeakageText").textContent = "-";
  $("regionStatusText").textContent = "-";
  $("regionLabelmapText").textContent = "-";
}

async function generateMask() {
  setBusy(true);
  try {
    const mask = await apiGet("/api/mask");
    $("maskSourceText").textContent = mask.mask_source || "none";
    $("maskText").textContent = mask.reliable_for_3d ? "reliable brain mask" : "debug fallback mask";
    $("maskRatioText").textContent = String(mask.mask_ratio ?? "-");
    $("maskUniqueText").textContent = Array.isArray(mask.mask_unique_values) ? mask.mask_unique_values.join(", ") : "-";
    $("maskStatusText").textContent = mask.mask_status || "-";
    $("componentCountText").textContent = String(mask.component_count ?? "-");
    $("largestComponentText").textContent = String(mask.largest_component_ratio ?? "-");
    $("holeRatioText").textContent = String(mask.hole_ratio ?? "-");
    $("edgeLeakageText").textContent = mask.edge_leakage === true ? "yes" : (mask.edge_leakage === false ? "no" : "-");
    await refreshStatus();
    await refreshSlice();
  } finally {
    setBusy(false);
  }
}

function bindViewerControls() {
  $("loadButton").addEventListener("click", loadVolume);
  $("refreshSliceButton").addEventListener("click", refreshSlice);
  $("maskButton").addEventListener("click", generateMask);
  $("planeSelect").addEventListener("change", refreshSlice);
  $("maskToggle").addEventListener("change", refreshSlice);
  $("overlayTypeSelect").addEventListener("change", refreshSlice);
  $("regionSelect").addEventListener("change", refreshSlice);
  $("sliceRange").addEventListener("input", () => {
    $("sliceValue").value = $("sliceRange").value;
    refreshSlice();
  });
  $("sliceValue").addEventListener("change", () => {
    $("sliceRange").value = $("sliceValue").value;
    refreshSlice();
  });
}

async function bootViewer() {
  $("maskToggle").value = "1";
  $("overlayTypeSelect").value = "brain_mask";
  bindViewerControls();
  setBusy(true);
  try {
    await loadSeriesList();
    await loadVolume();
  } finally {
    setBusy(false);
  }
}

bootViewer().catch(showPageError);
