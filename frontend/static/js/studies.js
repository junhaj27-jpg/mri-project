function studyStatusLabel(status) {
  if (status === "ready") return "Ready";
  if (status === "reference_only") return "Reference";
  return status || "-";
}

async function loadStudies() {
  setBusy(true);
  try {
    const rows = await apiGet("/api/studies");
    const body = document.getElementById("studiesBody");
    body.innerHTML = "";

    if (!rows.length) {
      body.innerHTML = '<tr><td colspan="6">No DICOM series found.</td></tr>';
      return;
    }

    for (const row of rows) {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${row.study_label || "-"}</strong></td>
        <td>${row.section || "-"}</td>
        <td>${row.description || "-"}</td>
        <td>${row.file_count || 0}</td>
        <td>${row.shape || "-"}</td>
        <td>${studyStatusLabel(row.status)}</td>
      `;
      body.appendChild(tr);
    }
  } finally {
    setBusy(false);
  }
}

document.getElementById("refreshStudiesBtn")?.addEventListener("click", () => {
  loadStudies().catch(showPageError);
});

loadStudies().catch(showPageError);
