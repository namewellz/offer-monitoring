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
const updateAllButton = document.getElementById('update-all-button');
const updateRetailer = document.getElementById('update-retailer');
const updateStatus = document.getElementById('update-status');
const collectionHistory = document.getElementById('collection-history');
const historyRefresh = document.getElementById('history-refresh');
let statusTimer;

const retailerNames = {
  'arena-atacado': 'Arena Atacado', goodbom: 'GoodBom', atacadao: 'Atacadão',
  savegnago: 'Savegnago', davitta: 'Davitta', assai: 'Assaí',
  tenda: 'Tenda Atacado', 'sao-vicente': 'São Vicente'
};
const statusNames = {
  queued: 'Na fila', started: 'Em andamento', deferred: 'Aguardando', scheduled: 'Agendada',
  finished: 'Concluída', PARTIAL_SUCCESS: 'Parcial', SUCCESS: 'Concluída',
  failed: 'Falhou', stopped: 'Interrompida', canceled: 'Cancelada'
};

function showStatus(message, type = '') {
  updateStatus.className = `update-status visible ${type}`;
  updateStatus.textContent = message;
}

function formatJobTime(job) {
  const raw = job.ended_at || job.started_at || job.enqueued_at;
  if (!raw) return 'Horário indisponível';
  return new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(raw));
}

function renderCollectionHistory(jobs) {
  if (!collectionHistory) return;
  collectionHistory.replaceChildren();
  if (!jobs.length) {
    const empty = document.createElement('p');
    empty.className = 'muted';
    empty.textContent = 'Nenhuma atualização recente.';
    collectionHistory.appendChild(empty);
    return;
  }
  const list = document.createElement('ul');
  list.className = 'job-list';
  for (const job of jobs) {
    const item = document.createElement('li');
    const heading = document.createElement('div');
    heading.className = 'job-heading';
    const source = document.createElement('strong');
    source.textContent = retailerNames[job.retailer] || job.retailer || 'Fonte desconhecida';
    const badge = document.createElement('span');
    const displayStatus = job.outcome || job.status;
    badge.className = `job-status ${displayStatus || 'unknown'}`;
    badge.textContent = statusNames[displayStatus] || displayStatus || 'Desconhecido';
    heading.append(source, badge);
    const time = document.createElement('time');
    time.textContent = formatJobTime(job);
    item.append(heading, time);
    if (job.error) {
      const error = document.createElement('p');
      error.className = 'job-error';
      error.textContent = job.error;
      item.appendChild(error);
    }
    const warnings = job.warnings || [];
    for (const warning of warnings.slice(0, 3)) {
      const detail = document.createElement('p');
      detail.className = 'job-warning';
      detail.textContent = `${warning.scope}: ${warning.error}`;
      item.appendChild(detail);
    }
    if (warnings.length > 3) {
      const remaining = document.createElement('p');
      remaining.className = 'job-warning-count';
      remaining.textContent = `Mais ${warnings.length - 3} aviso(s) nesta coleta.`;
      item.appendChild(remaining);
    }
    list.appendChild(item);
  }
  collectionHistory.appendChild(list);
}

async function loadCollectionHistory() {
  if (!collectionHistory) return;
  if (historyRefresh) historyRefresh.disabled = true;
  try {
    const response = await fetch('/catalog/collections/jobs?limit=20', { cache: 'no-store' });
    if (!response.ok) throw new Error('Não foi possível carregar o histórico.');
    renderCollectionHistory((await response.json()).jobs || []);
  } catch (error) {
    collectionHistory.replaceChildren();
    const message = document.createElement('p');
    message.className = 'job-error';
    message.textContent = error.message;
    collectionHistory.appendChild(message);
  } finally {
    if (historyRefresh) historyRefresh.disabled = false;
  }
}

function setUpdateControlsDisabled(disabled) {
  if (updateButton) updateButton.disabled = disabled;
  if (updateAllButton) updateAllButton.disabled = disabled;
  if (updateRetailer) updateRetailer.disabled = disabled;
}

async function fetchJob(jobId) {
  const response = await fetch(`/catalog/collections/jobs/${encodeURIComponent(jobId)}`);
  if (!response.ok) throw new Error('Não foi possível consultar a atualização.');
  return response.json();
}

async function pollJobs(requestedJobs) {
  const jobs = await Promise.all(requestedJobs.map(item => fetchJob(item.job_id)));
  const labels = { queued: 'Na fila', started: 'Coletando dados', deferred: 'Aguardando', scheduled: 'Agendada' };
  const terminal = new Set(['finished', 'failed', 'stopped', 'canceled']);
  const finished = jobs.filter(job => job.status === 'finished').length;
  const partial = jobs.filter(job => job.status === 'finished' && job.outcome === 'PARTIAL_SUCCESS').length;
  const failed = jobs.filter(job => ['failed', 'stopped', 'canceled'].includes(job.status));
  const pending = jobs.filter(job => !terminal.has(job.status));

  if (!pending.length && !failed.length) {
    const message = partial
      ? `Atualização concluída com ${partial} fonte(s) parcial(is). Consulte o histórico abaixo.`
      : 'Atualização concluída. Recarregando os dados…';
    showStatus(message, partial ? '' : 'success');
    setTimeout(() => window.location.reload(), 1200);
    return;
  }

  if (!pending.length) {
    setUpdateControlsDisabled(false);
    const failedNames = failed.map(job => job.retailer).filter(Boolean).join(', ');
    showStatus(
      `${finished} fonte(s) concluída(s) e ${failed.length} com falha${failedNames ? `: ${failedNames}` : '.'} Veja os detalhes no histórico abaixo.`,
      'error'
    );
    loadCollectionHistory();
    return;
  }

  if (requestedJobs.length === 1) {
    showStatus(`${labels[pending[0].status] || 'Processando'}… Você pode continuar usando a página.`);
  } else {
    showStatus(`Atualizando todas as fontes: ${finished} de ${jobs.length} concluída(s), ${pending.length} em andamento.`);
  }
  statusTimer = setTimeout(() => pollJobs(requestedJobs).catch(handleUpdateError), 2500);
}

function handleUpdateError(error) {
  clearTimeout(statusTimer);
  setUpdateControlsDisabled(false);
  showStatus(error.message || 'Erro ao solicitar a atualização.', 'error');
}

updateButton?.addEventListener('click', async () => {
  clearTimeout(statusTimer);
  setUpdateControlsDisabled(true);
  showStatus('Enviando solicitação…');
  try {
    const response = await fetch(`/catalog/collections/${encodeURIComponent(updateRetailer.value)}`, { method: 'POST' });
    if (!response.ok) throw new Error((await response.json()).detail || 'Solicitação recusada.');
    const data = await response.json();
    await pollJobs([data]);
  } catch (error) { handleUpdateError(error); }
});

updateAllButton?.addEventListener('click', async () => {
  clearTimeout(statusTimer);
  setUpdateControlsDisabled(true);
  showStatus('Enfileirando todas as fontes…');
  try {
    const response = await fetch('/catalog/collections', { method: 'POST' });
    if (!response.ok) throw new Error((await response.json()).detail || 'Solicitação recusada.');
    const data = await response.json();
    if (!data.jobs?.length) throw new Error('Nenhuma fonte foi configurada para atualização.');
    showStatus(`${data.jobs.length} fontes foram enfileiradas. Acompanhando o progresso…`);
    await pollJobs(data.jobs);
  } catch (error) { handleUpdateError(error); }
});

historyRefresh?.addEventListener('click', loadCollectionHistory);
loadCollectionHistory();

document.querySelector('[data-open-update]')?.addEventListener('click', () => {
  updateCard?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  setTimeout(() => updateRetailer?.focus(), 450);
});
