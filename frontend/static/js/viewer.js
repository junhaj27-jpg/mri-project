const viewerState = {
  status: null,
  series: [],
};

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
  viewerState.status = status;
  $("sourceText").textContent = status.source || "-";
  $("shapeText").textContent = formatShape(status.shape);
  $("spacingText").textContent = formatSpacing(status.spacing);
  $("seriesText").textContent = status.info?.SeriesDescription || status.source_label || "-";
  if ($("disclaimer") && status.disclaimer) $("disclaimer").textContent = status.disclaimer;
  updateSliceLimit();
}

async function loadVolume() {
  setBusy(true);
  try {
    const key = encodeURIComponent($("seriesSelect").value);
    await apiGet(`/api/load?series_key=${key}`);
    await refreshStatus();
    resetMaskStatus();
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
  $("sliceTitle").textContent = `${plane.charAt(0).toUpperCase()}${plane.slice(1)} slice`;
  $("sliceImage").src = `/api/slice?plane=${encodeURIComponent(plane)}&index=${index}&mask=${mask}&t=${Date.now()}`;
}

function resetMaskStatus() {
  $("maskText").textContent = "not checked";
  $("maskRatioText").textContent = "-";
  $("maskUniqueText").textContent = "-";
  $("maskStatusText").textContent = "-";
}

async function generateMask() {
  setBusy(true);
  try {
    const mask = await apiGet("/api/mask");
    $("maskText").textContent = mask.reliable_for_3d ? "reliable brain mask" : "debug fallback mask";
    $("maskRatioText").textContent = String(mask.mask_ratio ?? "-");
    $("maskUniqueText").textContent = Array.isArray(mask.mask_unique_values) ? mask.mask_unique_values.join(", ") : "-";
    $("maskStatusText").textContent = mask.mask_status || "-";
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
