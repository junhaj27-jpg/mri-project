function value(id) {
  return document.getElementById(id).value.trim();
}

function payload() {
  return {
    patient_code: value('patientCode') || 'P001',
    body_region: value('bodyRegion') || 'BRAIN',
    dicom_root_path: value('dicomRootPath'),
    study_label_start: value('studyLabelStart') || null,
  };
}

function renderResult(title, data, error = false) {
  const box = document.getElementById('privateStatus');
  box.className = `mode-result ${error ? 'error-mode' : 'private-mode'}`;
  box.innerHTML = `
    <h2>${title}</h2>
    <pre>${escapeHtml(JSON.stringify(data, null, 2))}</pre>
  `;
}

async function run(action) {
  try {
    if (action === 'manifest') {
      renderResult('Manifest 조회 결과', await apiGet(`/api/private/manifest/${value('patientCode') || 'P001'}`));
      return;
    }
    const body = payload();
    const endpoint = action === 'pipeline' ? '/api/private/run-pipeline' : '/api/private/scan-dicom';
    if (action === 'pipeline') {
      body.auto_convert_nifti = true;
      body.auto_generate_mesh = false;
    }
    renderResult(action === 'pipeline' ? 'Pipeline 결과' : 'DICOM Scan 결과', await apiPost(endpoint, body));
  } catch (error) {
    renderResult('오류', { message: error.message }, true);
  }
}

document.getElementById('bodyRegion').addEventListener('change', (event) => {
  if (event.target.value === 'LUMBAR_SPINE') {
    document.getElementById('dicomRootPath').value = 'data/private/P001/lumbar/LUMBAR_T01';
    document.getElementById('studyLabelStart').value = 'LUMBAR_T01';
  } else {
    document.getElementById('dicomRootPath').value = 'data/private/P001/brain/BRAIN_T01';
    document.getElementById('studyLabelStart').value = 'BRAIN_T01';
  }
});

document.getElementById('scanBtn').addEventListener('click', () => run('scan'));
document.getElementById('pipelineBtn').addEventListener('click', () => run('pipeline'));
document.getElementById('manifestBtn').addEventListener('click', () => run('manifest'));
