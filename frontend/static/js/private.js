function value(id) {
  return document.getElementById(id).value.trim();
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
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
    <h2>${escapeHtml(title)}</h2>
    <pre>${escapeHtml(JSON.stringify(data, null, 2))}</pre>
  `;
}

function renderModelCard(model) {
  const sourceClass = model.source === 'huggingface' ? 'hf' : 'core';
  return `
    <article class="model-card ${sourceClass}">
      <div class="model-card-top">
        <span class="model-source">${escapeHtml(model.source)}</span>
        <span class="model-status">${escapeHtml(model.status)}</span>
      </div>
      <h4>${escapeHtml(model.name)}</h4>
      <p>${escapeHtml(model.task)}</p>
      <dl class="model-meta">
        <div><dt>model_id</dt><dd>${escapeHtml(model.model_id)}</dd></div>
        <div><dt>input</dt><dd>${escapeHtml(model.input)}</dd></div>
        <div><dt>output</dt><dd>${escapeHtml(model.output)}</dd></div>
      </dl>
      <p class="small">${escapeHtml(model.note)}</p>
      <code>${escapeHtml(model.runner_hint)}</code>
      <a class="model-link" href="${escapeHtml(model.url)}" target="_blank" rel="noreferrer">모델 페이지 열기</a>
    </article>
  `;
}

function renderModelCatalog(catalog) {
  const box = document.getElementById('modelCatalog');
  const summary = document.getElementById('modelCatalogSummary');
  const stacks = catalog.stacks || [];
  summary.textContent = `${catalog.selected_body_region || 'ALL'} 기준 ${catalog.stack_count || 0}개 스택, ${catalog.model_count || 0}개 모델 후보를 표시합니다. 모델 파일은 다운로드하지 않았습니다.`;

  if (!stacks.length) {
    box.innerHTML = '<div class="model-empty">선택한 영역에 맞는 모델 후보가 없습니다.</div>';
    return;
  }

  box.innerHTML = stacks.map((stack) => `
    <section class="model-stack">
      <div class="model-stack-heading">
        <span class="mode-chip ${stack.mode === 'PUBLIC_DEMO' ? 'demo' : 'private'}">${escapeHtml(stack.mode)}</span>
        <div>
          <h3>${escapeHtml(stack.title)}</h3>
          <p>${escapeHtml(stack.summary)}</p>
        </div>
      </div>
      <ul class="model-tags">
        ${(stack.recommended_for || []).map((item) => `<li>${escapeHtml(item)}</li>`).join('')}
      </ul>
      <div class="model-grid">
        ${(stack.models || []).map(renderModelCard).join('')}
      </div>
    </section>
  `).join('');
}

async function loadModelCatalog() {
  const region = value('bodyRegion') || 'BRAIN';
  const catalog = await apiGet(`/api/private/model-catalog?body_region=${encodeURIComponent(region)}`);
  renderModelCatalog(catalog);
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
  loadModelCatalog().catch((error) => {
    document.getElementById('modelCatalog').innerHTML = `<div class="model-empty">모델 카탈로그 오류: ${escapeHtml(error.message)}</div>`;
  });
});

document.getElementById('scanBtn').addEventListener('click', () => run('scan'));
document.getElementById('pipelineBtn').addEventListener('click', () => run('pipeline'));
document.getElementById('manifestBtn').addEventListener('click', () => run('manifest'));
document.getElementById('refreshModelsBtn').addEventListener('click', () => loadModelCatalog());

loadModelCatalog().catch((error) => {
  document.getElementById('modelCatalog').innerHTML = `<div class="model-empty">모델 카탈로그 오류: ${escapeHtml(error.message)}</div>`;
});
