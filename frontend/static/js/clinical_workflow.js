const REGION_CONFIG = {
  brain: {
    label: 'Brain MRI',
    chip: 'Brain MRI Review',
    title: 'Brain MRI 종양 추적 리뷰',
    description: 'Brain MRI는 target region tracking, segmentation overlay, volume trend를 중심으로 검토합니다.',
    preview: '/sample_data/kaggle_2d_demo/brain_mri/tumor/mock_brain_tumor.png',
    overlay: '/sample_data/kaggle_2d_demo/masks/mock_brain_mri_tumor_overlay.png',
    purpose: 'Tumor tracking',
    timelineTitle: 'Brain Longitudinal Tracking',
    volumeHint: 'cm3',
    defaultStudy: 'T08',
    studyPrefix: 'T',
    qa: ['병변 경계 확인', 'artifact / motion 영향 확인', '동일 sequence 비교 확인', '전문의 최종 확인'],
    memo: 'Brain MRI private NIfTI/DICOM 기반 분석 결과는 원본 영상, segmentation mask, volume trend를 함께 검토해야 합니다.',
  },
  lumbar: {
    label: 'Lumbar Spine MRI',
    chip: 'Lumbar MRI Review',
    title: 'Lumbar Spine MRI 정상/참고 리뷰',
    description: 'Lumbar MRI는 디스크/협착 진단이 아니라 spine region, disc-level, 구조 확인 중심의 private review로 다룹니다.',
    preview: '/sample_data/kaggle_2d_demo/lumbar_mri/normal/mock_lumbar_normal.png',
    overlay: '/sample_data/kaggle_2d_demo/masks/mock_lumbar_mri_normal_overlay.png',
    purpose: 'Spine region review',
    timelineTitle: 'Lumbar Reference Review',
    volumeHint: 'reference',
    defaultStudy: 'LUMBAR_T01',
    studyPrefix: 'LUMBAR_',
    qa: ['척추 레벨 확인', 'sagittal/axial 방향 확인', 'artifact / motion 영향 확인', '전문의 최종 확인'],
    memo: 'Lumbar MRI는 정상/참고용 spine region review로 관리합니다. 디스크, 협착, 신경 압박에 대한 확정 진단 표현은 사용하지 않습니다.',
  },
};

const studySelect = document.getElementById('studySelect');
const bodyRegionSelect = document.getElementById('bodyRegion');
const previewImg = document.getElementById('clinicalPreview');
const overlayImg = document.getElementById('clinicalOverlay');
const opacitySlider = document.getElementById('opacitySlider');
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

function currentRegion() {
  return bodyRegionSelect.value || 'brain';
}

function currentConfig() {
  return REGION_CONFIG[currentRegion()];
}

function isLumbarStudy(study) {
  const text = `${study.study_label || ''} ${study.event_type || ''} ${study.section || ''}`.toLowerCase();
  return text.includes('lumbar') || text.includes('spine');
}

function regionStudies() {
  const region = currentRegion();
  return studies.filter((study) => region === 'lumbar' ? isLumbarStudy(study) : !isLumbarStudy(study));
}

function selectedStudy() {
  const rows = regionStudies();
  return rows.find((row) => row.study_label === studySelect.value) || rows[0] || null;
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
  if (!studies.length || !studies.some(isLumbarStudy)) {
    studies = await apiPost('/api/studies/seed');
  }
  tracking = await apiGet('/api/tracking').catch(() => []);
}

function renderSeriesOptions() {
  const region = currentRegion();
  const seriesType = document.getElementById('seriesType');
  Array.from(seriesType.options).forEach((option) => {
    option.hidden = option.dataset.region && option.dataset.region !== region;
  });
  const firstVisible = Array.from(seriesType.options).find((option) => !option.hidden);
  if (firstVisible) seriesType.value = firstVisible.value;
}

function renderStudySelect() {
  const config = currentConfig();
  const rows = regionStudies();
  studySelect.innerHTML = rows.map((study) => (
    `<option value="${escapeHtml(study.study_label)}">${escapeHtml(study.study_label)} - ${escapeHtml(study.event_type)}</option>`
  )).join('');

  if (rows.find((study) => study.study_label === config.defaultStudy)) {
    studySelect.value = config.defaultStudy;
  }
}

function renderRegionText() {
  const config = currentConfig();
  document.getElementById('regionChip').textContent = config.chip;
  document.getElementById('workspaceTitle').textContent = config.title;
  document.getElementById('workspaceDescription').textContent = config.description;
  document.getElementById('metricRegion').textContent = config.label;
  document.getElementById('metricPurpose').textContent = config.purpose;
  document.getElementById('timelineTitle').textContent = config.timelineTitle;
  document.getElementById('metricVolumeHint').textContent = config.volumeHint;
  document.getElementById('qcBoundaryText').textContent = config.qa[0];
  document.getElementById('qcArtifactsText').textContent = config.qa[1];
  document.getElementById('qcSeriesText').textContent = config.qa[2];
  document.getElementById('qcClinicianText').textContent = config.qa[3];
}

function renderImages() {
  const config = currentConfig();
  const study = selectedStudy();
  const previewUrl = study?.preview_url || config.preview;
  const overlayUrl = study?.overlay_url || config.overlay;

  previewImg.src = previewUrl;
  previewImg.dataset.fallback = config.preview;
  overlayImg.src = overlayUrl;
  overlayImg.dataset.fallback = config.preview;
  overlayImg.style.opacity = imageMode === 'overlay' ? String(Number(opacitySlider.value) / 100) : '0';
  window.applyImageFallback?.(document.getElementById('clinicalImageStage'));
}

function renderMetrics() {
  const study = selectedStudy();
  const config = currentConfig();
  document.getElementById('metricStudy').textContent = study?.study_label || '-';
  document.getElementById('metricEvent').textContent = study?.event_type || '-';
  document.getElementById('metricVolume').textContent = study?.volume_cm3 ?? (currentRegion() === 'lumbar' ? 'N/A' : '-');
  document.getElementById('metricPurpose').textContent = config.purpose;
  document.getElementById('metricStatus').textContent = reviewStatusLabel();
}

function renderTimeline() {
  const region = currentRegion();
  const rows = region === 'lumbar'
    ? regionStudies()
    : (tracking.length ? tracking.filter((row) => !isLumbarStudy(row)) : regionStudies());

  const max = Math.max(...rows.map((row) => row.volume_cm3 || 0), 1);
  document.getElementById('clinicalChart').innerHTML = rows.map((row) => {
    const width = row.volume_cm3 ? ((row.volume_cm3 || 0) / max) * 100 : 18;
    const isSelected = row.study_label === studySelect.value;
    return `
      <div class="bar-row ${isSelected ? 'selected-bar' : ''}">
        <div class="bar-label">${escapeHtml(row.study_label)}</div>
        <div class="bar" style="width:${width}%"></div>
        <div class="small">${row.volume_cm3 ? `${row.volume_cm3} cm3` : 'reference review'}</div>
      </div>`;
  }).join('');

  document.getElementById('clinicalTimelineRows').innerHTML = rows.map((row) => `
    <tr class="${row.study_label === studySelect.value ? 'selected-row' : ''}">
      <td><b>${escapeHtml(row.study_label)}</b></td>
      <td>${row.volume_cm3 ?? 'N/A'}</td>
      <td>${signedValue(row.change_cm3, ' cm3')}</td>
    </tr>
  `).join('');
}

function renderReport() {
  const study = selectedStudy();
  const config = currentConfig();
  const checks = [
    [config.qa[0], document.getElementById('qcBoundary').checked],
    [config.qa[1], document.getElementById('qcArtifacts').checked],
    [config.qa[2], document.getElementById('qcSeries').checked],
    [config.qa[3], document.getElementById('qcClinician').checked],
  ].map(([label, checked]) => `${label}: ${checked ? '확인' : '미확인'}`).join('\n');

  reportEl.value = [
    `[MRI Review Note]`,
    `Patient code: ${document.getElementById('patientCode').value || study?.patient_code || 'P001'}`,
    `Body region: ${config.label}`,
    `Study: ${study?.study_label || '-'}`,
    `Series: ${document.getElementById('seriesType').value}`,
    `Event: ${study?.event_type || '-'}`,
    `Volume: ${study?.volume_cm3 ?? 'N/A'} ${currentRegion() === 'lumbar' ? '(reference review)' : 'cm3'}`,
    `Change: ${signedValue(study?.change_cm3, ' cm3')} (${signedValue(study?.change_rate_percent, '%')})`,
    `Review status: ${reviewStatusLabel()}`,
    ``,
    `[Review Scope]`,
    config.memo,
    ``,
    `[QA]`,
    checks,
    ``,
    `[Memo]`,
    study?.memo || config.memo,
    ``,
    `Note: 이 문서는 판독 보조 초안이며 최종 진단/치료 판단을 대체하지 않습니다.`,
  ].join('\n');
}

function renderAll() {
  renderRegionText();
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
  const lower = file.name.toLowerCase();
  if (lower.includes('lumbar') || lower.includes('spine') || lower.includes('허리')) {
    bodyRegionSelect.value = 'lumbar';
    handleRegionChange();
  }
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

function handleRegionChange() {
  renderSeriesOptions();
  renderStudySelect();
  renderAll();
}

document.getElementById('seedBtn').addEventListener('click', async () => {
  studies = await apiPost('/api/studies/seed');
  tracking = await apiGet('/api/tracking').catch(() => []);
  handleRegionChange();
});
bodyRegionSelect.addEventListener('change', handleRegionChange);
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
    renderSeriesOptions();
    renderStudySelect();
    renderAll();
  })
  .catch((error) => {
    reportEl.value = `데이터를 불러오지 못했습니다.\n${error.message}`;
  });
