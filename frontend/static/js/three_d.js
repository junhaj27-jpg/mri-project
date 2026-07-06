const threeState = {
  status: null,
  series: [],
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
  $3("sourceText").textContent = status.source || "-";
  $3("shapeText").textContent = formatShape(status.shape);
  $3("spacingText").textContent = formatSpacing(status.spacing);
  $3("seriesText").textContent = status.info?.SeriesDescription || status.source_label || "-";
  $3("meshText").textContent = status.mesh_available ? "available" : "not generated";
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
    const sigma = encodeURIComponent($3("sigmaInput").value);
    const smooth = encodeURIComponent($3("smoothInput").value);
    const downsample = encodeURIComponent($3("downsampleInput").value);
    const meta = await apiGet(`/api/mesh?sigma=${sigma}&smooth=${smooth}&downsample=${downsample}&step=1`);
    $3("meshText").textContent = `${meta.vertices} vertices / ${meta.faces} faces`;
    $3("meshFrame").src = `/api/mesh_plot?sigma=${sigma}&smooth=${smooth}&downsample=${downsample}&step=1&t=${Date.now()}`;
  } finally {
    setBusy(false);
  }
}

function bindThreeControls() {
  $3("loadButton").addEventListener("click", loadThreeVolume);
  $3("meshButton").addEventListener("click", generateMesh);
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
    if (threeState.status?.mesh_available) {
      $3("meshFrame").src = `/api/mesh_plot?t=${Date.now()}`;
    }
  } finally {
    setBusy(false);
  }
}

bootThree().catch(showPageError);
