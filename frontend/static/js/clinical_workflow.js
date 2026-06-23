const PUBLIC_PREVIEW_URL = '/sample_data/kaggle_2d_demo/brain_mri/tumor/mock_brain_tumor.png';
const PUBLIC_OVERLAY_URL = '/sample_data/kaggle_2d_demo/masks/mock_brain_mri_tumor_overlay.png';

const studySelect = document.getElementById('studySelect');
const previewImg = document.getElementById('clinicalPreview');
const overlayImg = document.getElementById('clinicalOverlay');
const opacitySlider = document.getElementById('opacitySlider');
const sliceSlider = document.getElementById('sliceSlider');
const reportEl = document.getElementById('clinicalReport');

let studies = [];
let tracking = [];
let imageMode = 'overlay';

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  }[char]));
}

function selectedStudy() {
  return studies.find((row) => row.study_label === studySelect.value) || studies[0] || null;
}

function signedValue(value, suffix = '') {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-';
  const numeric = Number(value);
  return `${numeric > 0 ? '+' : ''}${numeric}${suffix}`;
}

function reviewStatusLabel() {
  const value = document.getElementById('reviewStatus').value;
  if (value === 'clinician_verified') return 'Verified';
  if (value === 'needs_correction') return 'Needs correction';
  return 'Draft';
}

async function ensureStudies() {
  studies = await apiGet('/api/studies');
  if (!studies.length) {
    studies = await apiPost('/api/studies/seed');
  }
  tracking = await apiGet('/api/tracking').catch(() => []);
}

function renderStudySelect() {
  studySelect.innerHTML = studies.map((study) => (
    `<option value="${escapeHtml(study.study_label)}">${escapeHtml(study.study_label)} - ${escapeHtml(study.event_type)}</option>`
  )).join('');
  if (studies.find((study) => study.study_label === 'T08')) studySelect.value = 'T08';
}

function renderImages() {
  const study = selectedStudy();
  const previewUrl = study?.preview_url || PUBLIC_PREVIEW_URL;
  const overlayUrl = study?.overlay_url || PUBLIC_OVERLAY_URL;

  previewImg.src = previewUrl;
  overlayImg.src = overlayUrl;
  overlayImg.style.opacity = imageMode === 'overlay' ? String(Number(opacitySlider.value) / 100) : '0';
  window.applyImageFallback?.(document.getElementById('clinicalImageStage'));
}

function renderMetrics() {
  const study = selectedStudy();
  if (!study) return;
  document.getElementById('metricStudy').textContent = study.study_label;
  document.getElementById('metricEvent').textContent = study.event_type || '-';
  document.getElementById('metricVolume').textContent = study.volume_cm3 ?? '-';
  document.getElementById('metricChange').textContent = signedValue(study.change_cm3, ' cm3');
  document.getElementById('metricStatus').textContent = reviewStatusLabel();
}

function renderTimeline() {
  const rows = tracking.length ? tracking : studies;
  const max = Math.max(...rows.map((row) => row.volume_cm3 || 0), 1);
  document.getElementById('clinicalChart').innerHTML = rows.map((row) => {
    const width = ((row.volume_cm3 || 0) / max) * 100;
    const isSelected = row.study_label === studySelect.value;
    return `
      <div class="bar-row ${isSelected ? 'selected-bar' : ''}">
        <div class="bar-label">${escapeHtml(row.study_label)}</div>
        <div class="bar" style="width:${width}%"></div>
        <div class="small">${row.volume_cm3 || '-'} cm3</div>
      </div>`;
  }).join('');

  document.getElementById('clinicalTimelineRows').innerHTML = rows.map((row) => `
    <tr class="${row.study_label === studySelect.value ? 'selected-row' : ''}">
      <td><b>${escapeHtml(row.study_label)}</b></td>
      <td>${row.volume_cm3 ?? '-'}</td>
      <td>${signedValue(row.change_cm3, ' cm3')}</td>
    </tr>
  `).join('');
}

function renderReport() {
  const study = selectedStudy();
  if (!study) return;
  const checks = [
    ['병변 경계', document.getElementById('qcBoundary').checked],
    ['artifact/motion 영향', document.getElementById('qcArtifacts').checked],
    ['동일 sequence 비교', document.getElementById('qcSeries').checked],
    ['전문의 최종 확인', document.getElementById('qcClinician').checked],
  ].map(([label, checked]) => `${label}: ${checked ? '확인' : '미확인'}`).join('\n');

  reportEl.value = [
    `[MRI Review Note]`,
    `Patient code: ${document.getElementById('patientCode').value || study.patient_code || 'P001'}`,
    `Study: ${study.study_label}`,
    `Series: ${document.getElementById('seriesType').value}`,
    `Event: ${study.event_type || '-'}`,
    `Volume: ${study.volume_cm3 ?? '-'} cm3`,
    `Change: ${signedValue(study.change_cm3, ' cm3')} (${signedValue(study.change_rate_percent, '%')})`,
    `Review status: ${reviewStatusLabel()}`,
    ``,
    `[Segmentation QA]`,
    checks,
    ``,
    `[Memo]`,
    study.memo || 'Private NIfTI/DICOM 기반 분석 결과를 원본 영상과 함께 검토해야 합니다.',
    ``,
    `Note: 이 문서는 판독 보조 초안이며 최종 진단/치료 판단을 대체하지 않습니다.`,
  ].join('\n');
}

function renderAll() {
  renderImages();
  renderMetrics();
  renderTimeline();
  renderReport();
}

function extensionOf(filename) {
  const lower = filename.toLowerCase();
  if (lower.endsWith('.nii.gz')) return '.nii.gz';
  const index = lower.lastIndexOf('.');
  return index === -1 ? '' : lower.slice(index);
}

function renderUploadRoute(payload) {
  const route = payload.route || {};
  const result = payload.result || {};
  const isDemo = route.mode === 'demo';
  const uploadResult = document.getElementById('uploadResult');
  uploadResult.className = `mode-result compact-result ${isDemo ? 'demo-mode' : 'private-mode'}`;
  uploadResult.innerHTML = `
    <h2>${isDemo ? 'Public Demo Mode' : 'Private Analysis Mode'}</h2>
    <p class="small"><code>${escapeHtml(route.filename)}</code> -> ${escapeHtml(route.file_kind)}</p>
    <ul class="feature-list compact-feature-list">${(route.enabled_features || []).map((feature) => `<li>${escapeHtml(feature)}</li>`).join('')}</ul>
    <p class="small">${escapeHtml(result.notice || payload.notice || '분류 완료')}</p>
  `;
}

async function handleUpload(file) {
  if (!file) return;
  const ext = extensionOf(file.name);
  if (['.jpg', '.jpeg', '.png'].includes(ext)) {
    previewImg.src = URL.createObjectURL(file);
    imageMode = 'preview';
  }
  try {
    renderUploadRoute(await apiUpload('/api/analysis/upload', file));
  } catch (error) {
    document.getElementById('uploadResult').className = 'mode-result compact-result error-mode';
    document.getElementById('uploadResult').innerHTML = `<h2>분류 실패</h2><p>${escapeHtml(error.message)}</p>`;
  }
}

function renderKaggleResult(payload) {
  const report = payload.report || {};
  const files = (report.sample_files || []).map((file) => `<li><code>${escapeHtml(file)}</code></li>`).join('');
  const box = document.getElementById('kaggleImportResult');
  box.hidden = false;
  box.className = 'kaggle-result success';
  box.innerHTML = `
    <strong>${Number(report.imported_count || 0)} files imported</strong>
    <p class="small"><code>${escapeHtml(report.dataset)}</code> -> <code>${escapeHtml(report.target_dir)}</code></p>
    ${files ? `<ul>${files}</ul>` : '<p class="small">복사된 JPG/PNG가 없습니다.</p>'}
  `;
}

function renderKaggleError(message) {
  const box = document.getElementById('kaggleImportResult');
  box.hidden = false;
  box.className = 'kaggle-result error';
  box.innerHTML = `<strong>Kaggle 다운로드 실패</strong><p>${escapeHtml(message)}</p>`;
}

async function importKaggle() {
  const dataset = document.getElementById('kaggleDataset').value.trim();
  if (!dataset) {
    renderKaggleError('Kaggle dataset slug를 입력하세요. 예: owner/dataset-name');
    return;
  }
  const [anatomy, label] = document.getElementById('kaggleTarget').value.split('/');
  const maxFilesValue = document.getElementById('kaggleMaxFiles').value.trim();
  const btn = document.getElementById('kaggleImportBtn');
  const box = document.getElementById('kaggleImportResult');
  btn.disabled = true;
  btn.textContent = 'Downloading...';
  box.hidden = false;
  box.className = 'kaggle-result loading';
  box.innerHTML = '<strong>Kaggle에서 직접 다운로드 중입니다...</strong><p class="small">대용량 데이터셋은 시간이 걸릴 수 있습니다.</p>';
  try {
    const payload = await apiPost('/api/analysis/kaggle-direct-import', {
      dataset,
      anatomy,
      label,
      max_files: maxFilesValue ? Number(maxFilesValue) : null,
      generate_reference_masks: true,
      keep_raw: false,
    });
    renderKaggleResult(payload);
  } catch (error) {
    renderKaggleError(error.message);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Download';
  }
}

document.getElementById('seedBtn').addEventListener('click', async () => {
  studies = await apiPost('/api/studies/seed');
  tracking = await apiGet('/api/tracking').catch(() => []);
  renderStudySelect();
  renderAll();
});
studySelect.addEventListener('change', renderAll);
document.getElementById('previewBtn').addEventListener('click', () => {
  imageMode = 'preview';
  renderImages();
});
document.getElementById('overlayBtn').addEventListener('click', () => {
  imageMode = 'overlay';
  renderImages();
});
opacitySlider.addEventListener('input', renderImages);
sliceSlider.addEventListener('input', () => {
  document.getElementById('viewerStatus')?.remove();
});
document.getElementById('reviewStatus').addEventListener('change', renderAll);
document.querySelectorAll('.segmentation-qc input').forEach((input) => input.addEventListener('change', renderReport));
document.getElementById('generateReportBtn').addEventListener('click', renderReport);
document.getElementById('copyReportBtn').addEventListener('click', async () => {
  await navigator.clipboard?.writeText(reportEl.value);
});
document.getElementById('modeUpload').addEventListener('change', (event) => handleUpload(event.target.files?.[0]));
document.getElementById('kaggleImportBtn').addEventListener('click', importKaggle);

ensureStudies()
  .then(() => {
    renderStudySelect();
    renderAll();
  })
  .catch((error) => {
    reportEl.value = `데이터를 불러오지 못했습니다.\n${error.message}`;
  });
