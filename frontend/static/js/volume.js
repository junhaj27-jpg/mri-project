function formatNumber(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return Number(value).toFixed(digits);
}

function renderVolumeChart(items) {
  const chart = document.getElementById("volumeChart");
  const max = Math.max(...items.map((item) => Number(item.volume_cm3) || 0), 1);
  chart.innerHTML = "";

  for (const item of items) {
    const row = document.createElement("div");
    row.className = "bar-row";
    const width = Math.max(4, ((Number(item.volume_cm3) || 0) / max) * 100);
    row.innerHTML = `
      <span class="bar-label">${item.study_label}</span>
      <span class="bar-track"><span class="bar" style="width:${width}%"></span></span>
      <strong>${formatNumber(item.volume_cm3, 1)} cm3</strong>
    `;
    chart.appendChild(row);
  }
}

function renderVolumeTable(items) {
  const body = document.getElementById("volumeBody");
  body.innerHTML = "";
  for (const item of items) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><strong>${item.study_label}</strong></td>
      <td>${formatNumber(item.volume_cm3, 2)}</td>
      <td>${formatNumber(item.change_cm3, 2)}</td>
      <td>${formatNumber(item.change_rate_percent, 2)}</td>
      <td>${item.quality_flag || "-"}</td>
    `;
    body.appendChild(tr);
  }
}

async function loadVolume() {
  setBusy(true);
  try {
    const [tracking, result] = await Promise.all([
      apiGet("/api/tracking"),
      apiGet("/api/volume-result"),
    ]);
    const mask = result.mask_volume || {};
    document.getElementById("maskVoxelText").textContent = mask.available ? mask.voxel_count.toLocaleString() : "Not available";
    document.getElementById("maskMm3Text").textContent = mask.available ? `${formatNumber(mask.volume_mm3, 2)} mm3` : "-";
    document.getElementById("maskMlText").textContent = mask.available ? `${formatNumber(mask.volume_ml, 3)} ml` : "-";
    document.getElementById("formulaText").textContent = result.formula || "-";
    renderVolumeChart(tracking.items || []);
    renderVolumeTable(tracking.items || []);
  } finally {
    setBusy(false);
  }
}

document.getElementById("refreshVolumeBtn")?.addEventListener("click", () => {
  loadVolume().catch(showPageError);
});

loadVolume().catch(showPageError);
