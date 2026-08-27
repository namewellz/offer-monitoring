const table = document.getElementById('catalog-table');
const sorting = [];
const numeric = new Set(['previous', 'current', 'change']);

if (table) {
  for (const header of table.querySelectorAll('th.sortable')) {
    header.addEventListener('click', () => {
      const key = header.dataset.key;
      const existing = sorting.find(item => item.key === key);
      if (!existing) sorting.push({ key, direction: 'asc' });
      else if (existing.direction === 'asc') existing.direction = 'desc';
      else sorting.splice(sorting.indexOf(existing), 1);
      const rows = [...table.tBodies[0].querySelectorAll('tr[data-product]')];
      rows.sort((left, right) => {
        for (const item of sorting) {
          let a = left.dataset[item.key] || '';
          let b = right.dataset[item.key] || '';
          if (numeric.has(item.key)) { a = Number(a); b = Number(b); }
          const comparison = typeof a === 'number' ? a - b : a.localeCompare(b, 'pt-BR');
          if (comparison) return item.direction === 'asc' ? comparison : -comparison;
        }
        return 0;
      });
      rows.forEach(row => table.tBodies[0].appendChild(row));
      table.querySelectorAll('th.sortable').forEach(item => {
        const sort = sorting.find(value => value.key === item.dataset.key);
        item.querySelector('.sort-indicator')?.remove();
        item.removeAttribute('aria-sort');
        if (sort) {
          item.setAttribute('aria-sort', sort.direction === 'asc' ? 'ascending' : 'descending');
          const marker = document.createElement('span');
          marker.className = 'sort-indicator';
          marker.textContent = `${sorting.indexOf(sort) + 1}${sort.direction === 'asc' ? '↑' : '↓'}`;
          item.appendChild(marker);
        }
      });
    });
  }
}

const updateCard = document.getElementById('manual-update');
const updateButton = document.getElementById('update-button');
const updateRetailer = document.getElementById('update-retailer');
const updateStatus = document.getElementById('update-status');
let statusTimer;

function showStatus(message, type = '') {
  updateStatus.className = `update-status visible ${type}`;
  updateStatus.textContent = message;
}

async function pollJob(jobId) {
  const response = await fetch(`/catalog/collections/jobs/${encodeURIComponent(jobId)}`);
  if (!response.ok) throw new Error('Não foi possível consultar a atualização.');
  const job = await response.json();
  const labels = { queued: 'Na fila', started: 'Coletando dados', deferred: 'Aguardando', scheduled: 'Agendada' };
  if (job.status === 'finished') {
    showStatus('Atualização concluída. Recarregando os dados…', 'success');
    setTimeout(() => window.location.reload(), 1200);
    return;
  }
  if (job.status === 'failed' || job.status === 'stopped' || job.status === 'canceled') {
    updateButton.disabled = false;
    showStatus(job.error || 'A atualização não pôde ser concluída.', 'error');
    return;
  }
  showStatus(`${labels[job.status] || 'Processando'}… Você pode continuar usando a página.`);
  statusTimer = setTimeout(() => pollJob(jobId).catch(handleUpdateError), 2500);
}

function handleUpdateError(error) {
  clearTimeout(statusTimer);
  updateButton.disabled = false;
  showStatus(error.message || 'Erro ao solicitar a atualização.', 'error');
}

updateButton?.addEventListener('click', async () => {
  clearTimeout(statusTimer);
  updateButton.disabled = true;
  showStatus('Enviando solicitação…');
  try {
    const response = await fetch(`/catalog/collections/${encodeURIComponent(updateRetailer.value)}`, { method: 'POST' });
    if (!response.ok) throw new Error((await response.json()).detail || 'Solicitação recusada.');
    const data = await response.json();
    await pollJob(data.job_id);
  } catch (error) { handleUpdateError(error); }
});

document.querySelector('[data-open-update]')?.addEventListener('click', () => {
  updateCard?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  setTimeout(() => updateRetailer?.focus(), 450);
});
