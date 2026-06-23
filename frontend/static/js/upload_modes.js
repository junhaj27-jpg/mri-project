const uploadInput = document.getElementById('modeUpload');
const uploadResult = document.getElementById('uploadResult');
const uploadPreview = document.getElementById('uploadPreview');
const seedBtn = document.getElementById('seedBtn');
const kaggleImportBtn = document.getElementById('kaggleImportBtn');
const kaggleDataset = document.getElementById('kaggleDataset');
const kaggleTarget = document.getElementById('kaggleTarget');
const kaggleMaxFiles = document.getElementById('kaggleMaxFiles');
const kaggleImportResult = document.getElementById('kaggleImportResult');


function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  }[char]));
}

function renderKaggleImport(payload) {
  const report = payload.report || {};
  const sampleFiles = (report.sample_files || [])
    .map((file) => `<li><code>${escapeHtml(file)}</code></li>`)
    .join('');

  kaggleImportResult.hidden = false;
  kaggleImportResult.className = 'kaggle-result success';
  kaggleImportResult.innerHTML = `
    <strong>${Number(report.imported_count || 0)} files imported</strong>
    <p class="small"><code>${escapeHtml(report.dataset)}</code> -> <code>${escapeHtml(report.target_dir)}</code></p>
    <p class="small">Manifest: <code>${escapeHtml(report.manifest_path)}</code></p>
    ${sampleFiles ? `<ul>${sampleFiles}</ul>` : '<p class="small">No JPG/PNG files were copied from this dataset.</p>'}
  `;
}

function renderKaggleError(message) {
  kaggleImportResult.hidden = false;
  kaggleImportResult.className = 'kaggle-result error';
  kaggleImportResult.innerHTML = `<strong>Kaggle import failed</strong><p>${escapeHtml(message)}</p>`;
}

function extensionOf(filename) {
  const lower = filename.toLowerCase();
  if (lower.endsWith('.nii.gz')) return '.nii.gz';
  const index = lower.lastIndexOf('.');
  return index === -1 ? '' : lower.slice(index);
}

function renderRoute(payload) {
  const route = payload.route || payload;
  const result = payload.result || {};
  const isDemo = route.mode === 'demo';
  uploadResult.className = `mode-result ${isDemo ? 'demo-mode' : 'private-mode'}`;

  const features = (route.enabled_features || []).map((feature) => `<li>${feature}</li>`).join('');
  const detail = isDemo
    ? `<div class="result-grid"><div class="metric-card"><span>Anatomy</span><strong>${result.public_category?.anatomy || 'brain_mri'}</strong><small>public dataset</small></div><div class="metric-card"><span>Label</span><strong>${result.classification?.predicted_label || 'tumor'}</strong><small>brain tumor / lumbar reference</small></div><div class="metric-card"><span>Mask</span><strong>${result.masking?.mask_label || 'tumor'}</strong><small>2D public reference mask</small></div><div class="metric-card"><span>Confidence</span><strong>${Math.round((result.classification?.confidence || 0.82) * 100)}%</strong><small>placeholder</small></div></div>`
    : `<pre>${JSON.stringify({
        slice_viewer: result.slice_viewer,
        brain_extraction: result.brain_extraction,
        tumor_segmentation: result.tumor_segmentation,
        mesh_generation: result.mesh_generation,
        volume_measurement: result.volume_measurement,
        longitudinal_tracking: result.longitudinal_tracking,
      }, null, 2)}</pre>`;

  uploadResult.innerHTML = `
    <h2>${isDemo ? 'Public Demo Mode' : 'Private Analysis Mode'}</h2>
    <p class="small"><code>${route.filename}</code> -> ${route.file_kind}</p>
    <ul class="feature-list">${features}</ul>
    ${detail}
  `;
}

function renderLocalPreview(file) {
  const ext = extensionOf(file.name);
  if (['.jpg', '.jpeg', '.png'].includes(ext)) {
    uploadPreview.src = URL.createObjectURL(file);
    uploadPreview.alt = 'Uploaded 2D MRI preview';
    return;
  }
  uploadPreview.src = '/assets/mri-banner.png';
  uploadPreview.alt = 'Private MRI analysis placeholder';
}

uploadInput?.addEventListener('change', async () => {
  const file = uploadInput.files?.[0];
  if (!file) return;
  renderLocalPreview(file);

  try {
    const payload = await apiUpload('/api/analysis/upload', file);
    renderRoute(payload);
  } catch (error) {
    uploadResult.className = 'mode-result error-mode';
    uploadResult.innerHTML = `<h2>Unsupported Upload</h2><p>${error.message}</p>`;
  }
});


kaggleImportBtn?.addEventListener('click', async () => {
  const dataset = kaggleDataset?.value.trim();
  if (!dataset) {
    renderKaggleError('Enter a Kaggle dataset slug such as owner/dataset-name.');
    return;
  }

  const [anatomy, label] = (kaggleTarget?.value || 'brain_mri/tumor').split('/');
  const maxValue = kaggleMaxFiles?.value.trim();
  const maxFiles = maxValue ? Number(maxValue) : null;

  kaggleImportBtn.disabled = true;
  kaggleImportBtn.textContent = 'Downloading...';
  kaggleImportResult.hidden = false;
  kaggleImportResult.className = 'kaggle-result loading';
  kaggleImportResult.innerHTML = '<strong>Downloading from Kaggle...</strong><p class="small">This can take a while for large datasets.</p>';

  try {
    const payload = await apiPost('/api/analysis/kaggle-direct-import', {
      dataset,
      anatomy,
      label,
      max_files: maxFiles,
      generate_reference_masks: true,
      keep_raw: false,
    });
    renderKaggleImport(payload);
  } catch (error) {
    renderKaggleError(error.message);
  } finally {
    kaggleImportBtn.disabled = false;
    kaggleImportBtn.textContent = 'Download';
  }
});

async function loadDashboard() {
  try {
    const rows = await apiGet('/api/studies');
    document.getElementById('studyCount').textContent = rows.length;
    const latest = rows.filter((row) => row.volume_cm3).at(-1);
    document.getElementById('latestVolume').textContent = latest ? latest.volume_cm3 : '-';
  } catch {
    document.getElementById('studyCount').textContent = '0';
    document.getElementById('latestVolume').textContent = '-';
  }
}

seedBtn?.addEventListener('click', async () => {
  await apiPost('/api/studies/seed');
  await loadDashboard();
});

loadDashboard();
