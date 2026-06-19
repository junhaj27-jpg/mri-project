async function loadVolume() {
  const rows = await apiGet('/api/tracking');
  document.getElementById('volumeRows').innerHTML = rows.map(r => `
    <tr>
      <td><b>${r.study_label}</b></td>
      <td>${formatValue(r.volume_cm3)}</td>
      <td>${formatValue(r.change_cm3)}</td>
      <td>${formatValue(r.change_rate_percent, '%')}</td>
      <td>${r.event_type}</td>
    </tr>`).join('');

  const max = Math.max(...rows.map(r => r.volume_cm3 || 0), 1);
  document.getElementById('chart').innerHTML = rows.map(r => {
    const width = ((r.volume_cm3 || 0) / max) * 100;
    return `<div class="bar-row"><div class="bar-label">${r.study_label}</div><div class="bar" style="width:${width}%"></div><div class="small">${r.volume_cm3 || '-'} cm³</div></div>`;
  }).join('');
}
loadVolume().catch(() => {
  document.getElementById('volumeRows').innerHTML = '<tr><td colspan="5">샘플 데이터를 먼저 생성하세요.</td></tr>';
});
