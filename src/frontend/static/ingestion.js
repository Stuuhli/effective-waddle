(function (global) {
  'use strict';

  const PLACEHOLDER_TEXT = JSON.stringify({ status: 'waiting for run' });
  const PIPELINE_STEPS = ['docling', 'chunking', 'embeddings', 'citations'];
  const DELETE_ICON =
    '<svg xmlns="http://www.w3.org/2000/svg" height="24" viewBox="0 -960 960 960" width="24" fill="currentColor"><path d="M280-120q-33 0-56.5-23.5T200-200v-520h-40v-80h200v-40h240v40h200v80h-40v520q0 33-23.5 56.5T680-120H280Zm400-600H280v520h400v-520ZM360-280h80v-360h-80v360Zm160 0h80v-360h-80v360ZM280-720v520-520Z"/></svg>';

  function init() {
    const utils = global.FrontendUtils;
    if (!utils) {
      console.warn('FrontendUtils is unavailable; ingestion console features are disabled.');
      return;
    }

    const elements = {
      fileInput: document.getElementById('file-input'),
      fileBrowse: document.getElementById('file-browse'),
      fileClear: document.getElementById('file-clear'),
      dropzone: document.getElementById('dropzone'),
      fileList: document.getElementById('file-list'),
      runWorkflow: document.getElementById('run-workflow'),
      resetWorkflow: document.getElementById('reset-workflow'),
      configForm: document.getElementById('ingestion-config'),
      pipeline: document.getElementById('pipeline'),
      previewDocling: document.querySelector('#preview-docling pre'),
      previewChunks: document.querySelector('#preview-chunks pre'),
      previewCitations: document.querySelector('#preview-citations pre'),
      jobTableBody: document.getElementById('job-table-body'),
      ingestionHeader: document.getElementById('ingestion-header'),
      workflowPanel: document.getElementById('workflow-panel'),
      collectionSelect: document.getElementById('collection-select'),
      refreshJobs: document.getElementById('refresh-jobs'),
    };

    const requiredKeys = ['fileInput', 'fileBrowse', 'fileClear', 'dropzone', 'fileList', 'runWorkflow', 'resetWorkflow', 'configForm', 'pipeline', 'jobTableBody'];
    const missing = requiredKeys.filter((key) => !elements[key]);
    if (missing.length) {
      console.error('Ingestion workspace markup is incomplete; aborting initialisation.', missing);
      return;
    }

    const { isAdmin, fetchWithAuth } = utils;
    let queue = [];

    function updateRunButtonState() {
      if (!elements.runWorkflow) {
        return;
      }
      const hasFiles = queue.length > 0;
      const hasCollection = elements.collectionSelect ? Boolean(elements.collectionSelect.value) : true;
      elements.runWorkflow.disabled = !(hasFiles && hasCollection);
    }

    if (!isAdmin()) {
      if (elements.workflowPanel) {
        elements.workflowPanel.hidden = true;
      }
      const leadParagraph = elements.ingestionHeader?.querySelector('.workspace-header__lead p');
      if (leadParagraph) {
        leadParagraph.textContent =
          'Upload PDFs to request ingestion. Administrators can run Docling workflows or review jobs in the console.';
      }
    }

    elements.collectionSelect?.addEventListener('change', (event) => {
      const target = event.target;
      if (!(target instanceof HTMLSelectElement) || !elements.configForm) {
        return;
      }
      const option = target.selectedOptions[0];
      if (!option) {
        return;
      }
      const size = Number(option.dataset.defaultSize);
      const overlap = Number(option.dataset.defaultOverlap);
      const chunkSize = elements.configForm.querySelector('input[name="chunk_size"]');
      const chunkOverlap = elements.configForm.querySelector('input[name="chunk_overlap"]');
      if (chunkSize && !Number.isNaN(size) && size > 0) {
        chunkSize.value = String(size);
      }
      if (chunkOverlap && !Number.isNaN(overlap) && overlap >= 0) {
        chunkOverlap.value = String(overlap);
      }
      updateRunButtonState();
    });

    function updateQueueView() {
      if (!elements.fileList || !elements.runWorkflow || !elements.fileClear) {
        return;
      }
      elements.fileList.innerHTML = '';
      if (!queue.length) {
        elements.fileList.innerHTML = '<li class="file-list__empty">No documents queued yet.</li>';
        elements.fileClear.disabled = true;
        updateRunButtonState();
        return;
      }

      queue.forEach((file, index) => {
        const item = document.createElement('li');
        item.className = 'file-list__item';
        const sizeInMb = (file.size / 1024 / 1024).toFixed(2);
        item.innerHTML = `
          <span>
            <strong>${file.name}</strong>
            <small>${sizeInMb} MB</small>
          </span>
          <button class="chip" data-index="${index}" type="button">Remove</button>
        `;
        elements.fileList.appendChild(item);
      });

      elements.fileClear.disabled = false;
      updateRunButtonState();
    }

    function addFiles(list) {
      if (!list) {
        return;
      }
      const pdfs = Array.from(list).filter((file) => file.type === 'application/pdf');
      queue = queue.concat(pdfs);
      updateQueueView();
    }

    elements.fileBrowse.addEventListener('click', () => elements.fileInput?.click());
    elements.fileInput.addEventListener('change', (event) => addFiles(event.target?.files));

    elements.fileClear.addEventListener('click', () => {
      queue = [];
      updateQueueView();
    });

    elements.fileList.addEventListener('click', (event) => {
      const target = event.target;
      const button = target instanceof HTMLElement ? target.closest('button[data-index]') : null;
      if (!button) {
        return;
      }
      const index = Number(button.dataset.index);
      if (Number.isNaN(index)) {
        return;
      }
      queue.splice(index, 1);
      updateQueueView();
    });

    function highlightDropzone(active) {
      elements.dropzone.classList.toggle('dropzone--active', Boolean(active));
    }

    elements.dropzone.addEventListener('dragover', (event) => {
      event.preventDefault();
      highlightDropzone(true);
    });

    elements.dropzone.addEventListener('dragleave', () => highlightDropzone(false));

    elements.dropzone.addEventListener('drop', (event) => {
      event.preventDefault();
      highlightDropzone(false);
      addFiles(event.dataTransfer?.files);
    });

    elements.dropzone.addEventListener('click', () => elements.fileInput?.click());
    elements.dropzone.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        elements.fileInput?.click();
      }
    });

    function setStepStatus(step, status, detail) {
      const element = elements.pipeline.querySelector(`[data-step="${step}"]`);
      if (!element) {
        return;
      }
      element.classList.remove('pipeline__step--pending', 'pipeline__step--running', 'pipeline__step--done', 'pipeline__step--error');
      element.classList.add(`pipeline__step--${status}`);
      const statusLabel = element.querySelector('.pipeline__status');
      if (statusLabel) {
        statusLabel.textContent = status.charAt(0).toUpperCase() + status.slice(1);
      }
      if (detail) {
        const paragraph = element.querySelector('.pipeline__content p');
        if (paragraph) {
          paragraph.textContent = detail;
        }
      }
    }

    function resetPipeline() {
      PIPELINE_STEPS.forEach((step) => setStepStatus(step, 'pending'));
      if (elements.previewDocling) {
        elements.previewDocling.textContent = PLACEHOLDER_TEXT;
      }
      if (elements.previewChunks) {
        elements.previewChunks.textContent = PLACEHOLDER_TEXT;
      }
      if (elements.previewCitations) {
        elements.previewCitations.textContent = PLACEHOLDER_TEXT;
      }
    }

    elements.resetWorkflow.addEventListener('click', () => {
      queue = [];
      updateQueueView();
      resetPipeline();
    });

    const stepMap = {
      docling_parse: 'docling',
      chunk_assembly: 'chunking',
      embedding_indexing: 'embeddings',
      citation_enrichment: 'citations',
    };

    function pipelineStatus(status) {
      switch (status) {
        case 'running':
          return 'running';
        case 'success':
          return 'done';
        case 'failed':
          return 'error';
        default:
          return 'pending';
      }
    }

    function describeEvent(event) {
      if (!event || !event.detail) {
        return undefined;
      }
      const detail = event.detail;
      switch (event.step) {
        case 'docling_parse':
          return detail.documents !== undefined ? `Parsed ${detail.documents} document(s)` : undefined;
        case 'chunk_assembly':
          return detail.chunks !== undefined ? `Chunks: ${detail.chunks}` : undefined;
        case 'embedding_indexing':
          return detail.chunks_embedded !== undefined ? `Embedded ${detail.chunks_embedded} chunk(s)` : undefined;
        case 'citation_enrichment':
          return Array.isArray(detail.citations) ? `Citations linked: ${detail.citations.length}` : undefined;
        default:
          return undefined;
      }
    }

    function updatePreviews(events, config) {
      events.forEach((event) => {
        if (!event.detail) {
          return;
        }
        if (event.step === 'docling_parse' && elements.previewDocling) {
          elements.previewDocling.textContent = JSON.stringify(event.detail, null, 2);
        }
        if (event.step === 'chunk_assembly' && elements.previewChunks) {
          const detail = { chunk_size: config.chunk_size, chunk_overlap: config.chunk_overlap, ...event.detail };
          elements.previewChunks.textContent = JSON.stringify(detail, null, 2);
        }
        if (event.step === 'embedding_indexing' && elements.previewChunks) {
          try {
            const current = elements.previewChunks.textContent ? JSON.parse(elements.previewChunks.textContent) : {};
            elements.previewChunks.textContent = JSON.stringify({ ...current, ...event.detail }, null, 2);
          } catch (error) {
            elements.previewChunks.textContent = JSON.stringify(event.detail, null, 2);
          }
        }
        if (event.step === 'citation_enrichment' && elements.previewCitations) {
          elements.previewCitations.textContent = JSON.stringify(event.detail, null, 2);
        }
      });
    }

    function applyJobState(job, config) {
      if (!job || !Array.isArray(job.events)) {
        return;
      }
      updatePreviews(job.events, config);
      job.events.forEach((event) => {
        const stepKey = stepMap[event.step];
        if (!stepKey) {
          return;
        }
        setStepStatus(stepKey, pipelineStatus(event.status), describeEvent(event));
      });
      if (job.status === 'failed') {
        setStepStatus('citations', 'error', job.error_message || 'Ingestion failed');
      }
    }

    function appendJobRow(job) {
      const body = elements.jobTableBody;
      if (!body) {
        return;
      }
      const emptyRow = body.querySelector('.job-table__empty-row');
      if (emptyRow) {
        emptyRow.remove();
      }
      let row = body.querySelector(`tr[data-job-id="${job.id}"]`);
      if (!row) {
        row = document.createElement('tr');
        row.dataset.jobId = job.id;
        row.innerHTML = `
          <td class="job-id"></td>
          <td class="job-source"></td>
          <td class="job-collection"></td>
          <td class="job-status"></td>
          <td class="job-updated"></td>
          <td class="job-actions">
            <button
              class="icon-button icon-button--danger"
              type="button"
              data-action="delete-job"
              data-job-id="${job.id}"
              aria-label="Delete document ${job.source}"
              title="Delete document">
              ${DELETE_ICON}
            </button>
          </td>
        `;
        body.prepend(row);
      }
      const statusMarkup = `<span class="status-pill status-pill--${job.status}">${job.status}</span>`;
      row.querySelector('.job-id').textContent = job.id;
      row.querySelector('.job-source').textContent = job.source;
      row.querySelector('.job-collection').textContent = job.collection;
      row.querySelector('.job-status').innerHTML = statusMarkup;
      row.querySelector('.job-updated').textContent = job.updated_at;
      const deleteButton = row.querySelector('button[data-action="delete-job"]');
      if (deleteButton) {
        deleteButton.dataset.jobId = job.id;
        deleteButton.setAttribute('aria-label', `Delete document ${job.source}`);
        deleteButton.title = 'Delete document';
      }
    }

    function renderJobEmptyState() {
      const body = elements.jobTableBody;
      if (!body) {
        return;
      }
      if (body.querySelector('tr')) {
        return;
      }
      const row = document.createElement('tr');
      row.className = 'job-table__empty-row';
      row.innerHTML = '<td colspan="6" class="job-table__empty">No ingested documents yet.</td>';
      body.appendChild(row);
    }

    async function submitJobs(config) {
      const body = new FormData();
      queue.forEach((file) => body.append('files', file));
      body.append('collection', config.collection);
      body.append('chunk_size', String(config.chunk_size));
      body.append('chunk_overlap', String(config.chunk_overlap));
      body.append(
        'metadata',
        JSON.stringify({ include_tables: config.include_tables, generate_citations: config.generate_citations })
      );

      const response = await fetchWithAuth('/ingestion/jobs/upload', { method: 'POST', body });
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || 'Ingestion request failed');
      }
      return response.json();
    }

    async function pollJob(jobId, config) {
      let complete = false;
      while (!complete) {
        const response = await fetchWithAuth(`/ingestion/jobs/${jobId}`, {
          headers: { Accept: 'application/json' },
        });
        if (!response.ok) {
          throw new Error('Failed to fetch job status');
        }
        const job = await response.json();
        applyJobState(job, config);
        appendJobRow({
          id: job.id,
          source: job.source,
          collection: job.collection_name,
          status: job.status,
          updated_at: new Date(job.updated_at).toLocaleString(),
        });
        complete = job.status === 'success' || job.status === 'failed';
        if (!complete) {
          // eslint-disable-next-line no-await-in-loop
          await new Promise((resolve) => global.setTimeout(resolve, 2000));
        }
      }
    }

    elements.runWorkflow.addEventListener('click', async () => {
      if (!elements.configForm) {
        return;
      }
      const formData = new FormData(elements.configForm);
      const collectionValue = String(formData.get('collection') ?? '').trim();
      if (!collectionValue) {
        elements.collectionSelect?.focus();
        updateRunButtonState();
        return;
      }
      const config = {
        chunk_size: Number(formData.get('chunk_size')),
        chunk_overlap: Number(formData.get('chunk_overlap')),
        collection: collectionValue,
        include_tables: formData.get('include_tables') === 'on',
        generate_citations: formData.get('generate_citations') === 'on',
      };

      resetPipeline();
      if (elements.previewChunks) {
        elements.previewChunks.textContent = JSON.stringify(
          { chunk_size: config.chunk_size, chunk_overlap: config.chunk_overlap },
          null,
          2
        );
      }

      try {
        elements.runWorkflow.disabled = true;
        const jobs = await submitJobs(config);
        queue = [];
        updateQueueView();
        await Promise.all(jobs.map((job) => pollJob(job.id, config)));
      } catch (error) {
        console.error(error);
        setStepStatus('docling', 'error', 'Upload failed');
      } finally {
        updateRunButtonState();
      }
    });

    elements.refreshJobs?.addEventListener('click', async () => {
      try {
        const [collectionsResponse, jobsResponse] = await Promise.all([
          fetchWithAuth('/ingestion/collections', { headers: { Accept: 'application/json' } }),
          fetchWithAuth('/ingestion/jobs', { headers: { Accept: 'application/json' } }),
        ]);

        if (!collectionsResponse.ok) {
          throw new Error('Failed to refresh collections');
        }
        if (!jobsResponse.ok) {
          throw new Error('Failed to fetch jobs');
        }

        if (elements.collectionSelect) {
          const collectionsData = await collectionsResponse.json();
          const previousValue = elements.collectionSelect.value;
          elements.collectionSelect.innerHTML = '<option value="">Select a collection…</option>';
          let hasPreviousValue = false;
          collectionsData.forEach((item) => {
            const option = document.createElement('option');
            option.value = item.name;
            option.dataset.defaultSize = item.default_chunk_size;
            option.dataset.defaultOverlap = item.default_chunk_overlap;
            option.textContent = `${item.name} • ${item.document_count} docs`;
            if (item.name === previousValue) {
              hasPreviousValue = true;
            }
            elements.collectionSelect.appendChild(option);
          });
          elements.collectionSelect.value = hasPreviousValue ? previousValue : '';
          updateRunButtonState();
        } else {
          await collectionsResponse.json();
        }

        const jobsData = await jobsResponse.json();
        if (elements.jobTableBody) {
          elements.jobTableBody.innerHTML = '';
          jobsData.forEach((job) => {
            appendJobRow({
              id: job.id,
              source: job.source,
              collection: job.collection_name,
              status: job.status,
              updated_at: new Date(job.updated_at).toLocaleString(),
            });
          });
          renderJobEmptyState();
        }
      } catch (error) {
        console.error(error);
        setStepStatus('docling', 'error', error.message || 'Unable to refresh job list');
      }
    });

    elements.jobTableBody?.addEventListener('click', async (event) => {
      const target = event.target;
      if (!(target instanceof Element)) {
        return;
      }
      const button = target.closest('button[data-action="delete-job"]');
      if (!button) {
        return;
      }
      const jobId = button.dataset.jobId || '';
      if (!jobId) {
        return;
      }
      const row = button.closest('tr');
      const label = row?.querySelector('.job-source')?.textContent?.trim() || jobId;
      if (!global.confirm(`Delete "${label}" and remove all related artefacts?`)) {
        return;
      }

      button.disabled = true;
      try {
        const response = await fetchWithAuth(`/ingestion/jobs/${jobId}`, { method: 'DELETE' });
        if (!response.ok) {
          const message = await response.text();
          throw new Error(message || `Failed with status ${response.status}`);
        }
        row?.remove();
        renderJobEmptyState();
      } catch (error) {
        console.error('Failed to delete ingestion job', error);
        global.alert(
          error instanceof Error
            ? `Unable to delete document: ${error.message}`
            : 'Unable to delete document.',
        );
      } finally {
        button.disabled = false;
      }
    });

    updateQueueView();
    updateRunButtonState();
    renderJobEmptyState();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
})(window);
