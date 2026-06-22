async function loadVolume() {
  const rows = await apiGet('/api/tracking');
  document.getElementById('volumeRows').innerHTML = rows.map((row) => `
    <tr>
      <td><b>${row.study_label}</b></td>
      <td>${formatValue(row.volume_cm3)}</td>
      <td>${formatValue(row.change_cm3)}</td>
      <td>${formatValue(row.change_rate_percent, '%')}</td>
      <td>${row.event_type}</td>
    </tr>`).join('');

  const max = Math.max(...rows.map((row) => row.volume_cm3 || 0), 1);
  document.getElementById('chart').innerHTML = rows.map((row) => {
    const width = ((row.volume_cm3 || 0) / max) * 100;
    return `<div class="bar-row"><div class="bar-label">${row.study_label}</div><div class="bar" style="width:${width}%"></div><div class="small">${row.volume_cm3 || '-'} cm3</div></div>`;
  }).join('');
}

loadVolume().catch(() => {
  document.getElementById('volumeRows').innerHTML = '<tr><td colspan="5">Mock 데이터를 먼저 생성하세요.</td></tr>';
});
