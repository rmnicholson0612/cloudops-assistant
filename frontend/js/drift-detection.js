// Drift Detection Module
// Contains all functions related to GitHub repository scanning and drift monitoring

// GitHub Repository Scanning Functions
async function scanRepos() {
    if (!API.requireAuth()) return;

    const target = document.getElementById('github-target').value;
    const githubToken = document.getElementById('github-token').value;

    if (!target) {
        alert('Please enter a GitHub username or organization');
        return;
    }

    API.showLoading('scan-results', 'Scanning repositories...');

    try {
        const result = await API.post('/scan-repos', {
            github_target: target,
            github_token: githubToken
        });
        displayScanResults(result.results || []);
    } catch (error) {
        API.showError('scan-results', error.message);
    }
}

function displayScanResults(repositories) {
    const resultsDiv = document.getElementById('scan-results');

    if (!repositories || repositories.length === 0) {
        resultsDiv.innerHTML = '<p>No terraform repositories found.</p>';
        return;
    }

    resultsDiv.innerHTML = '<h4>Found ' + repositories.length + ' terraform repositories:</h4>' +
        '<div class="repo-list">' +
        repositories.map(repo =>
            '<div class="repo-item">' +
                '<h5><i class="fab fa-github"></i> ' + (repo.repo_name || repo.name || 'Unknown Repository') + '</h5>' +
                '<p><strong>Status:</strong> ' + getStatusDisplay(repo.status, repo.error) + '</p>' +
                '<p><strong>Last scan:</strong> ' + (repo.last_scan ? new Date(repo.last_scan).toLocaleString() : 'Never') + '</p>' +
                getDriftDisplay(repo) +
                '<div class="repo-actions">' +
                    '<button class="btn btn-sm btn-primary" onclick="monitorRepo(' + JSON.stringify(repo).replace(/"/g, '&quot;') + ')">' +
                        '<i class="fas fa-eye"></i> Monitor' +
                    '</button>' +
                    (repo.repo_url ? '<a href="' + repo.repo_url + '" target="_blank" class="btn btn-sm btn-secondary">' +
                        '<i class="fas fa-external-link-alt"></i> View' +
                    '</a>' : '') +
                '</div>' +
            '</div>'
        ).join('') +
        '</div>';
}

function clearGitHubForm() {
    document.getElementById('github-target').value = '';
    document.getElementById('github-token').value = '';
    document.getElementById('scan-results').innerHTML = 'Enter a GitHub username or organization to scan for terraform repositories...';
}

async function monitorRepo(repo) {
    if (!API.requireAuth()) return;

    try {
        await API.post('/drift/configure', {
            repo_name: repo.full_name || repo.repo_name || repo.name,
            github_url: repo.repo_url || repo.html_url || `https://github.com/${repo.full_name || repo.repo_name}`
        });
        alert(`Repository ${repo.full_name || repo.repo_name} is now being monitored for drift!`);
        // Refresh the drift status to show the newly added repo
        loadDriftStatus();
    } catch (error) {
        alert(`Failed to monitor repository: ${error.message}`);
    }
}

// Scheduled Drift Monitoring Functions
async function loadDriftStatus() {
    if (!API.isAuthenticated()) {
        API.showError('drift-status-display', 'Please login to view drift monitoring status');
        return;
    }

    try {
        const status = await API.get('/drift/status');
        displayDriftStatus(status);
    } catch (error) {
        API.showError('drift-status-display', 'No repositories being monitored for drift');
    }
}

function displayDriftStatus(status) {
    const display = document.getElementById('drift-status-display');
    const repos = status.configurations || [];

    if (repos.length === 0) {
        display.innerHTML = '<p>No repositories being monitored. Use "Scan Repositories" to find terraform repos to monitor.</p>';
        return;
    }

    display.innerHTML = '<div class="drift-repos">' +
            '<h4>Monitored Repositories (' + repos.length + ')</h4>' +
            repos.map(repo =>
                '<div class="drift-repo-item">' +
                    '<div class="repo-info">' +
                        '<h5>' + (repo.repo_name || repo.name) + '</h5>' +
                        '<p>Last check: ' + (repo.last_scan?.timestamp || 'Never') + '</p>' +
                        '<p>Status: ' + (repo.last_scan?.drift_detected ? '⚠️ Drift detected' : '✅ No drift') + '</p>' +
                        '<p>Schedule: ' + (repo.schedule || 'daily') + '</p>' +
                    '</div>' +
                    '<div class="repo-actions">' +
                        '<button class="btn btn-sm btn-primary" onclick="checkDrift(\'' + repo.config_id + '\')">' +
                            '<i class="fas fa-sync"></i> Check Now' +
                        '</button>' +
                        '<button class="btn btn-sm btn-secondary" onclick="editDriftConfig(\'' + repo.config_id + '\', ' + JSON.stringify(repo).replace(/"/g, '&quot;') + ')">' +
                            '<i class="fas fa-edit"></i> Edit' +
                        '</button>' +
                        '<button class="btn btn-sm btn-danger" onclick="deleteDriftConfig(\'' + repo.config_id + '\', \'' + (repo.repo_name || repo.name) + '\')">' +
                            '<i class="fas fa-trash"></i> Delete' +
                        '</button>' +
                    '</div>' +
                '</div>'
            ).join('') +
        '</div>';
}

async function checkDrift(configId) {
    if (!API.requireAuth()) return;

    try {
        // URL encode the config_id to handle special characters like #
        const encodedConfigId = encodeURIComponent(configId);
        await API.post(`/drift/scan/${encodedConfigId}`);
        alert(`Drift check completed`);
        loadDriftStatus(); // Refresh status
    } catch (error) {
        alert(`Drift check failed: ${error.message}`);
    }
}

function showDriftConfigModal() {
    alert('Drift configuration modal - Feature coming soon!');
}

async function editDriftConfig(configId, repo) {
    if (!API.requireAuth()) return;

    const newSchedule = prompt('Enter new schedule (hourly, daily, weekly):', repo.schedule || 'daily');
    if (!newSchedule) return;

    const validSchedules = ['hourly', 'daily', 'weekly'];
    if (!validSchedules.includes(newSchedule.toLowerCase())) {
        alert('Invalid schedule. Please use: hourly, daily, or weekly');
        return;
    }

    try {
        const encodedConfigId = encodeURIComponent(configId);
        await API.put(`/drift/update/${encodedConfigId}`, {
            schedule: newSchedule.toLowerCase()
        });
        alert(`Repository ${repo.repo_name || repo.name} schedule updated to ${newSchedule}`);
        loadDriftStatus(); // Refresh status
    } catch (error) {
        alert(`Failed to update repository: ${error.message}`);
    }
}

async function deleteDriftConfig(configId, repoName) {
    if (!API.requireAuth()) return;

    if (!confirm(`Are you sure you want to stop monitoring ${repoName}?`)) {
        return;
    }

    try {
        const encodedConfigId = encodeURIComponent(configId);
        await API.delete(`/drift/delete/${encodedConfigId}`);
        alert(`Repository ${repoName} is no longer being monitored`);
        loadDriftStatus(); // Refresh status
    } catch (error) {
        alert(`Failed to delete repository: ${error.message}`);
    }
}

// Helper functions for better display
function getStatusDisplay(status, error) {
    const statusMap = {
        'no_drift': '✅ No drift detected',
        'drift_detected': '⚠️ Drift detected',
        'no_terraform': '📁 No terraform files found',
        'init_failed': '❌ Terraform init failed',
        'timeout': '⏱️ Scan timeout',
        'error': '❌ Scan error'
    };

    let display = statusMap[status] || ('❓ ' + (status || 'Unknown'));
    if (status === 'error' && error) {
        display += ': ' + error;
    }
    return display;
}

function getDriftDisplay(repo) {
    if (repo.status === 'error') {
        return '<p class="text-danger">Error: ' + (repo.error || 'Unknown error occurred') + '</p>';
    }
    if (repo.status === 'init_failed') {
        return '<p class="text-warning">Terraform initialization failed. Check repository configuration.</p>';
    }
    if (repo.status === 'no_terraform') {
        return '<p class="text-info">Repository does not contain terraform files.</p>';
    }
    if (repo.status === 'timeout') {
        return '<p class="text-warning">Scan timed out. Repository may be too large or complex.</p>';
    }
    if (repo.drift_detected && repo.changes) {
        return '<p class="text-warning">⚠️ ' + repo.changes.length + ' changes detected</p>';
    }
    if (repo.status === 'no_drift') {
        return '<p class="text-success">✅ Infrastructure matches configuration</p>';
    }
    return '<p class="text-muted">Scan status unknown</p>';
}

// Initialize drift monitoring on page load
document.addEventListener('DOMContentLoaded', function() {
    loadDriftStatus();

    // Auto-populate GitHub form fields if defaults are configured
    if (window.CONFIG?.GITHUB_DEFAULT_TARGET) {
        const targetInput = document.getElementById('github-target');
        if (targetInput && !targetInput.value) {
            targetInput.value = window.CONFIG.GITHUB_DEFAULT_TARGET;
        }
    }

    if (window.CONFIG?.GITHUB_DEFAULT_TOKEN) {
        const tokenInput = document.getElementById('github-token');
        if (tokenInput && !tokenInput.value) {
            tokenInput.value = window.CONFIG.GITHUB_DEFAULT_TOKEN;
        }
    }

    // Auto-scan if both target and token are configured and user is authenticated
    if (API.isAuthenticated() && window.CONFIG?.GITHUB_DEFAULT_TARGET && window.CONFIG?.GITHUB_DEFAULT_TOKEN) {
        // Delay auto-scan to ensure UI is ready
        setTimeout(() => {
            const scanResults = document.getElementById('scan-results');
            if (scanResults && scanResults.innerHTML.includes('Enter a GitHub username')) {
                scanRepos();
            }
        }, 1000);
    }
});
