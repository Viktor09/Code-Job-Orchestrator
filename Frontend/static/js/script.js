let jobs = [];
let jobsRefreshTimer = null;

async function loadJobs() {
    const response = await fetch('/api/jobs');
    if (!response.ok) {
        throw new Error(`Failed to load jobs (${response.status})`);
    }
    jobs = await response.json();
    renderJobsTable();
}

function renderJobsTable() {
    const tbody = document.getElementById('jobsTableBody');
    if (!jobs.length) {
        tbody.innerHTML = '<tr><td colspan="5" class="empty-state">No jobs submitted yet</td></tr>';
        return;
    }
    tbody.innerHTML = '';
    jobs.forEach(job => {
        const row = tbody.insertRow();
        
        const cellId = row.insertCell(0);
        cellId.textContent = job.id;
        
        const cellExec = row.insertCell(1);
        cellExec.textContent = job.executableName;
        
        const cellStatus = row.insertCell(2);
        const statusSpan = document.createElement('span');
        statusSpan.className = `status-badge ${job.status}`;
        statusSpan.textContent = job.status.toUpperCase();
        cellStatus.appendChild(statusSpan);
        
        const cellDate = row.insertCell(3);
        cellDate.textContent = job.submittedAt ? new Date(job.submittedAt).toLocaleString() : '—';
        
        const cellActions = row.insertCell(4);
        const actionsDiv = document.createElement('div');
        actionsDiv.className = 'action-buttons';

        const logsBtn = document.createElement('button');
        logsBtn.textContent = 'Logs';
        logsBtn.className = 'btn-icon';
        logsBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            openLogModal(job.id);
        });

        actionsDiv.appendChild(logsBtn);
        cellActions.appendChild(actionsDiv);
    });
}

async function openLogModal(jobId) {
    const response = await fetch(`/api/jobs/${jobId}/log`);
    if (!response.ok) {
        document.getElementById('logContent').innerText = 'Unable to load logs.';
        document.getElementById('logModal').style.display = 'flex';
        return;
    }
    const payload = await response.json();
    const logsText = payload.logs || 'No logs available.';
    document.getElementById('logContent').innerText = logsText;
    document.getElementById('logModal').style.display = 'flex';
}

async function submitJobToOrchestrator(execFile, additionalFilesArray, jobLabelText) {
    const formData = new FormData();
    formData.append('executable', execFile);
    additionalFilesArray.forEach(file => formData.append('additional_files', file));
    formData.append('job_label', jobLabelText || '');

    const response = await fetch('/api/jobs', {
        method: 'POST',
        body: formData,
    });

    const payload = await response.json();
    if (!response.ok) {
        throw new Error(payload.message || payload.status || 'Submission failed');
    }

    await loadJobs();
    return payload;
}

function switchPage(pageId) {
    document.querySelectorAll('.page').forEach(page => page.classList.remove('active-page'));
    document.getElementById(`${pageId}Page`).classList.add('active-page');
    document.querySelectorAll('.nav-btn').forEach(btn => {
        if (btn.getAttribute('data-page') === pageId) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    });
    if (pageId === 'jobs') {
        loadJobs().catch(() => {
            renderJobsTable();
        });
        if (!jobsRefreshTimer) {
            jobsRefreshTimer = setInterval(() => {
                loadJobs().catch(() => {});
            }, 5000);
        }
    } else if (jobsRefreshTimer) {
        clearInterval(jobsRefreshTimer);
        jobsRefreshTimer = null;
    }
}

function closeModal() {
    document.getElementById('logModal').style.display = 'none';
}

document.addEventListener('DOMContentLoaded', () => {
    loadJobs().catch((err) => {
        document.getElementById('submitFeedback').innerHTML = `<span style="color:#b33;">${err.message}</span>`;
    });
    jobsRefreshTimer = setInterval(() => {
        loadJobs().catch(() => {});
    }, 5000);
    
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const externalUrl = btn.getAttribute('data-url');
            if (externalUrl) {
                window.open(externalUrl, '_blank', 'noopener');
                return;
            }

            const pageId = btn.getAttribute('data-page');
            if (pageId) {
                switchPage(pageId);
            }
        });
    });
    
    document.getElementById('closeModalBtn').addEventListener('click', closeModal);
    window.addEventListener('click', (e) => {
        if (e.target === document.getElementById('logModal')) closeModal();
    });
    
    const additionalFilesInput = document.getElementById('additionalFiles');
    const additionalFileListDiv = document.getElementById('additionalFileList');
    
    additionalFilesInput.addEventListener('change', (e) => {
        const files = Array.from(e.target.files);
        if (files.length === 0) {
            additionalFileListDiv.style.display = 'none';
            additionalFileListDiv.innerHTML = '';
            return;
        }
        additionalFileListDiv.style.display = 'block';
        additionalFileListDiv.innerHTML = files.map(f => `<div class="file-item">📎 ${f.name} (${(f.size/1024).toFixed(1)} KB)</div>`).join('');
    });
    
    const submitForm = document.getElementById('submitJobForm');
    submitForm.addEventListener('submit', async (event) => {
        event.preventDefault();
        const execFileInput = document.getElementById('executableFile');
        const execFile = execFileInput.files[0];
        if (!execFile) {
            document.getElementById('submitFeedback').innerHTML = '<span style="color:#b33;">Please select an executable file.</span>';
            return;
        }
        const additionalFiles = Array.from(document.getElementById('additionalFiles').files);
        const jobLabel = document.getElementById('jobLabel').value.trim();
        
        const submitBtn = document.querySelector('.btn-submit');
        const originalText = submitBtn.innerHTML;
        submitBtn.disabled = true;
        submitBtn.innerHTML = 'Submitting ...';
        
        try {
            const result = await submitJobToOrchestrator(execFile, additionalFiles, jobLabel);
            document.getElementById('submitFeedback').innerHTML = `<span style="color:#1f6e4a;">${result.message} (ID: ${result.jobId})</span>`;
            submitForm.reset();
            additionalFileListDiv.style.display = 'none';
            additionalFileListDiv.innerHTML = '';
            setTimeout(() => {
                switchPage('jobs');
                document.getElementById('submitFeedback').innerHTML = '';
            }, 1200);
        } catch (err) {
            document.getElementById('submitFeedback').innerHTML = `<span style="color:#b33;">Submission error: ${err.message}</span>`;
        } finally {
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalText;
        }
    });
});
