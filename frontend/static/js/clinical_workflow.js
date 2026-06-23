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
    qa: ['척추 레벨 확인', 'sagittal/axial 방향 확인', 'artifact / motion 영향 확인', '전문의 최종 확인'],
    memo: 'Lumbar MRI는 정상/참고용 spine region review로 관리합니다. 디스크, 협착, 신경 압박에 대한 확정 진단 표현은 사용하지 않습니다.',
  },
};

const WINDOW_PRESETS = {
  brain: { label: 'Brain WL/WW', brightness: 1.02, contrast: 1.18 },
  soft: { label: 'Soft tissue', brightness: 1.06, contrast: 1.04 },
  lumbar: { label: 'Spine WL/WW', brightness: 1.0, contrast: 1.28 },
};

const REGION_METADATA = {
  brain: { spacing: [0.9, 0.9, 1.2], slices: 120, source: 'Private NIfTI/DICOM' },
  lumbar: { spacing: [0.8, 0.8, 3.0], slices: 32, source: 'Private DICOM/NIfTI' },
};

const studySelect = document.getElementById('studySelect');
const bodyRegionSelect = document.getElementById('bodyRegion');
const regionTabs = Array.from(document.querySelectorAll('[data-region-tab]'));
const previewImg = document.getElementById('clinicalPreview');
const overlayImg = document.getElementById('clinicalOverlay');
const opacitySlider = document.getElementById('opacitySlider');
const sliceSlider = document.getElementById('sliceSlider');
const imageStage = document.getElementById('clinicalImageStage');
const windowButtons = Array.from(document.querySelectorAll('[data-window-preset]'));
const reportEl = document.getElementById('clinicalReport');

let studies = [];
let tracking = [];
let imageMode = 'overlay';
let activeWindowPreset = 'brain';
let imageInverted = false;
let measurementVisible = false;

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

function selectedRegionRows() {
  if (currentRegion() === 'brain' && tracking.length) {
    return tracking.filter((row) => !isLumbarStudy(row));
  }
  return regionStudies();
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

function metadataForStudy(study) {
  const defaults = REGION_METADATA[currentRegion()];
  const spacing = [
    study?.voxel_spacing_x ?? defaults.spacing[0],
    study?.voxel_spacing_y ?? defaults.spacing[1],
    study?.voxel_spacing_z ?? defaults.spacing[2],
  ];
  return {
    spacing,
    slices: study?.slice_count ?? defaults.slices,
    source: study?.is_sample_data ? 'Mock preview / private-ready' : defaults.source,
    modality: study?.modality || 'MRI',
  };
}

function versionedDemoAsset(url) {
  if (!url || !url.startsWith('/sample_data/kaggle_2d_demo/')) return url;
  return `${url}${url.includes('?') ? '&' : '?'}v=clinical-mock-2`;
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
  if (firstVisible && seriesType.selectedOptions[0]?.hidden) seriesType.value = firstVisible.value;
  if (firstVisible && !seriesType.value) seriesType.value = firstVisible.value;
}

function renderStudySelect() {
  const config = currentConfig();
  const rows = regionStudies();
  const previous = studySelect.value;
  studySelect.innerHTML = rows.map((study) => (
    `<option value="${escapeHtml(study.study_label)}">${escapeHtml(study.study_label)} - ${escapeHtml(study.event_type)}</option>`
  )).join('');

  if (rows.find((study) => study.study_label === previous)) {
    studySelect.value = previous;
  } else if (rows.find((study) => study.study_label === config.defaultStudy)) {
    studySelect.value = config.defaultStudy;
  }
}

function renderRegionText() {
  const config = currentConfig();
  regionTabs.forEach((button) => {
    const active = button.dataset.regionTab === currentRegion();
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', String(active));
  });
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

function renderViewportTools() {
  const preset = WINDOW_PRESETS[activeWindowPreset] || WINDOW_PRESETS.brain;
  const invert = imageInverted ? ' invert(1)' : '';
  previewImg.style.filter = `grayscale(1) brightness(${preset.brightness}) contrast(${preset.contrast})${invert}`;
  imageStage.classList.toggle('measurement-active', measurementVisible);
  document.getElementById('measurementOverlay').hidden = !measurementVisible;
  document.getElementById('viewportPreset').textContent = `${preset.label}${imageInverted ? ' / Invert' : ''}`;
  windowButtons.forEach((button) => {
    button.classList.toggle('active', button.dataset.windowPreset === activeWindowPreset);
  });
}

function renderViewportMeta() {
  const study = selectedStudy();
  const meta = metadataForStudy(study);
  const sliceCount = meta.slices || 1;
  if (Number(sliceSlider.max) !== sliceCount) sliceSlider.max = String(sliceCount);
  if (Number(sliceSlider.value) > sliceCount) sliceSlider.value = String(Math.ceil(sliceCount / 2));
  const sliceText = `${sliceSlider.value} / ${sliceCount}`;
  document.getElementById('metaModality').textContent = meta.modality;
  document.getElementById('metaSpacing').textContent = `${meta.spacing.join(' x ')} mm`;
  document.getElementById('metaSlice').textContent = sliceText;
  document.getElementById('metaSource').textContent = meta.source;
  document.getElementById('sliceHud').textContent = `Slice ${sliceText}`;
}

function renderImages() {
  const config = currentConfig();
  const study = selectedStudy();
  const previewUrl = versionedDemoAsset(study?.preview_url || config.preview);
  const overlayUrl = versionedDemoAsset(study?.overlay_url || config.overlay);

  previewImg.src = previewUrl;
  previewImg.dataset.fallback = versionedDemoAsset(config.preview);
  overlayImg.src = overlayUrl;
  overlayImg.dataset.fallback = versionedDemoAsset(config.preview);
  overlayImg.style.opacity = imageMode === 'overlay' ? String(Number(opacitySlider.value) / 100) : '0';
  window.applyImageFallback?.(imageStage);
  renderViewportTools();
  renderViewportMeta();
}

function renderMetrics() {
  const study = selectedStudy();
  const config = currentConfig();
  const patientCode = document.getElementById('patientCode').value || study?.patient_code || 'P001';
  document.getElementById('summaryPatient').textContent = patientCode;
  document.getElementById('summaryStudy').textContent = study?.study_label || '-';
  document.getElementById('summarySeries').textContent = document.getElementById('seriesType').value || '-';
  document.getElementById('summaryStatus').textContent = reviewStatusLabel();
  document.getElementById('metricStudy').textContent = study?.study_label || '-';
  document.getElementById('metricEvent').textContent = study?.event_type || '-';
  document.getElementById('metricVolume').textContent = study?.volume_cm3 ?? (currentRegion() === 'lumbar' ? 'N/A' : '-');
  document.getElementById('metricPurpose').textContent = config.purpose;
  document.getElementById('metricStatus').textContent = reviewStatusLabel();
}

function renderPriorComparison() {
  const rows = selectedRegionRows();
  const study = selectedStudy();
  const currentIndex = rows.findIndex((row) => row.study_label === study?.study_label);
  const prior = currentIndex > 0 ? rows[currentIndex - 1] : null;
  const summary = document.getElementById('comparisonSummary');

  if (!study) {
    summary.textContent = '선택된 검사가 없습니다.';
    return;
  }
  if (currentRegion() === 'lumbar') {
    summary.textContent = `${study.study_label}: 정상/참고용 spine review입니다. 디스크/협착 확정 진단 라벨로 사용하지 않습니다.`;
    return;
  }
  if (!prior) {
    summary.textContent = `${study.study_label}: 기준 검사로 표시합니다. 추적 판단은 이후 동일 시퀀스와 비교하세요.`;
    return;
  }
  const currentVolume = study.volume_cm3 ?? 'N/A';
  const priorVolume = prior.volume_cm3 ?? 'N/A';
  summary.textContent = `${prior.study_label} ${priorVolume} cm3 -> ${study.study_label} ${currentVolume} cm3, 변화 ${signedValue(study.change_cm3, ' cm3')} (${signedValue(study.change_rate_percent, '%')})`;
}

function renderTimeline() {
  const rows = selectedRegionRows();
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

function defaultFindings(study, config) {
  if (currentRegion() === 'lumbar') {
    return 'Lumbar spine MRI reference review. Alignment, disc-level coverage, motion artifact, and sagittal/axial correlation should be checked. No disc herniation or stenosis diagnosis label is assigned from public demo data.';
  }
  return `Brain MRI ${study?.study_label || ''} with segmentation overlay and longitudinal volume context. Target region boundary, enhancement pattern, and same-sequence prior comparison should be reviewed together.`;
}

function defaultImpression(study) {
  if (currentRegion() === 'lumbar') {
    return 'Normal/reference lumbar review workflow. Confirm with private DICOM/NIfTI study before clinical reporting.';
  }
  return `Tumor tracking review: volume ${study?.volume_cm3 ?? 'N/A'} cm3, change ${signedValue(study?.change_cm3, ' cm3')} (${signedValue(study?.change_rate_percent, '%')}).`;
}

function reportInputValue(id, fallback) {
  const el = document.getElementById(id);
  return el && el.value.trim() ? el.value.trim() : fallback;
}

function renderReport() {
  const study = selectedStudy();
  const config = currentConfig();
  const meta = metadataForStudy(study);
  const preset = WINDOW_PRESETS[activeWindowPreset] || WINDOW_PRESETS.brain;
  const findings = reportInputValue('reportFindings', defaultFindings(study, config));
  const impression = reportInputValue('reportImpression', defaultImpression(study));
  const recommendation = reportInputValue(
    'reportRecommendation',
    currentRegion() === 'lumbar' ? 'Private DICOM/NIfTI 기준으로 최종 판독 전 재확인' : '동일 시퀀스 prior와 추적 비교',
  );
  const critical = document.getElementById('criticalFlag')?.checked ? 'Yes' : 'No';
  const checks = [
    [config.qa[0], document.getElementById('qcBoundary').checked],
    [config.qa[1], document.getElementById('qcArtifacts').checked],
    [config.qa[2], document.getElementById('qcSeries').checked],
    [config.qa[3], document.getElementById('qcClinician').checked],
  ].map(([label, checked]) => `${label}: ${checked ? '확인' : '미확인'}`).join('\n');

  reportEl.value = [
    `[Radiology Review Draft]`,
    `Patient code: ${document.getElementById('patientCode').value || study?.patient_code || 'P001'}`,
    `Body region: ${config.label}`,
    `Study: ${study?.study_label || '-'}`,
    `Series: ${document.getElementById('seriesType').value}`,
    `Event: ${study?.event_type || '-'}`,
    `Volume: ${study?.volume_cm3 ?? 'N/A'} ${currentRegion() === 'lumbar' ? '(reference review)' : 'cm3'}`,
    `Change: ${signedValue(study?.change_cm3, ' cm3')} (${signedValue(study?.change_rate_percent, '%')})`,
    `Slice: ${sliceSlider.value} / ${meta.slices}`,
    `Spacing: ${meta.spacing.join(' x ')} mm`,
    `Window preset: ${preset.label}${imageInverted ? ' / Invert' : ''}`,
    `Review status: ${reviewStatusLabel()}`,
    `Critical finding flag: ${critical}`,
    ``,
    `[Findings]`,
    findings,
    ``,
    `[Impression]`,
    impression,
    ``,
    `[Recommendation]`,
    recommendation,
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
  renderPriorComparison();
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
    renderViewportTools();
    renderViewportMeta();
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
  activeWindowPreset = currentRegion() === 'lumbar' ? 'lumbar' : 'brain';
  imageInverted = false;
  measurementVisible = false;
  renderSeriesOptions();
  renderStudySelect();
  renderAll();
}

regionTabs.forEach((button) => {
  button.addEventListener('click', () => {
    bodyRegionSelect.value = button.dataset.regionTab;
    handleRegionChange();
  });
});

document.getElementById('patientCode').addEventListener('input', renderAll);
document.getElementById('seriesType').addEventListener('change', renderAll);
windowButtons.forEach((button) => {
  button.addEventListener('click', () => {
    activeWindowPreset = button.dataset.windowPreset;
    renderViewportTools();
    renderReport();
  });
});
document.getElementById('invertBtn').addEventListener('click', () => {
  imageInverted = !imageInverted;
  renderViewportTools();
  renderReport();
});
document.getElementById('measureBtn').addEventListener('click', () => {
  measurementVisible = !measurementVisible;
  renderViewportTools();
});
document.getElementById('resetViewBtn').addEventListener('click', () => {
  activeWindowPreset = currentRegion() === 'lumbar' ? 'lumbar' : 'brain';
  imageInverted = false;
  measurementVisible = false;
  imageMode = 'overlay';
  opacitySlider.value = '45';
  renderImages();
  renderReport();
});
sliceSlider.addEventListener('input', () => {
  renderViewportMeta();
  renderReport();
});
['reportFindings', 'reportImpression', 'reportRecommendation'].forEach((id) => {
  document.getElementById(id).addEventListener('input', renderReport);
});
document.getElementById('criticalFlag').addEventListener('change', renderReport);

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
