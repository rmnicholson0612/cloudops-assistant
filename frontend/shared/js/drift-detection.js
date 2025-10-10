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
        displayScanResults(result);
    } catch (error) {
        let errorMessage = error.message;

        // Provide specific guidance for common issues
        if (errorMessage.includes('GitHub token is invalid')) {
            errorMessage = 'GitHub token is invalid. Please check your token or remove it to scan public repositories only.';
        } else if (errorMessage.includes('rate limit')) {
            errorMessage = 'GitHub API rate limit exceeded. Please provide a valid GitHub token for higher limits (5000/hour vs 60/hour).';
        } else if (errorMessage.includes('No repositories found') || errorMessage.includes('no public repositories found')) {
            errorMessage = 'No repositories found. This could mean: 1) The username/organization doesn\'t exist, 2) They have no public repositories, or 3) Your GitHub token is invalid.';
        }

        API.showError('scan-results', errorMessage);
    }
}

function displayScanResults(data) {
    const resultsDiv = document.getElementById('scan-results');
    const repositories = data.results || [];

    if (!repositories || repositories.length === 0) {
        resultsDiv.innerHTML = '<p>No terraform repositories found.</p>';
        return;
    }

    // Check for token warning in first repository
    let warningHtml = '';
    if (repositories.length > 0 && repositories[0]._token_warning) {
        warningHtml = '<div style="background: #fff3cd; border: 1px solid #ffeaa7; border-radius: 4px; padding: 10px; margin-bottom: 15px; color: #856404;">' +
            '<i class="fas fa-exclamation-triangle"></i> <strong>Warning:</strong> ' + repositories[0]._token_warning +
            '</div>';
    }

    // Statistics summary
    const statsHtml = '<div class="scan-stats" style="background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 8px; padding: 15px; margin-bottom: 20px;">' +
        '<div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 15px;">' +
            '<div><strong>Total Repositories:</strong> ' + (data.total_repos || 0) + '</div>' +
            '<div><strong>Terraform Repositories:</strong> ' + (data.terraform_repos || 0) + '</div>' +
            '<div><strong>Monitored:</strong> ' + (data.monitored_repos || 0) + '</div>' +
            '<div style="color: ' + (data.coverage_percentage >= 80 ? '#28a745' : data.coverage_percentage >= 50 ? '#ffc107' : '#dc3545') + ';"><strong>Coverage:</strong> ' + (data.coverage_percentage || 0) + '%</div>' +
        '</div>' +
    '</div>';

    resultsDiv.innerHTML = warningHtml + statsHtml + '<h4>Terraform Repositories (' + repositories.length + '):</h4>' +
        '<div class="repo-list">' +
        repositories.map(repo =>
            '<div class="repo-item" style="display: flex; justify-content: space-between; align-items: center; border: 1px solid #dee2e6; border-radius: 8px; padding: 15px; margin-bottom: 10px; background: white;">' +
                '<div>' +
                    '<h5 style="margin: 0 0 5px 0;"><i class="fab fa-github"></i> ' + (repo.repo_name || repo.name || 'Unknown Repository') + '</h5>' +
                    '<div style="font-size: 14px; color: #666;">' +
                        (repo.is_monitored ? '<span style="color: #28a745;"><i class="fas fa-check-circle"></i> Monitored</span>' : '<span style="color: #6c757d;"><i class="fas fa-clock"></i> Not Monitored</span>') +
                        (repo.private ? ' • <i class="fas fa-lock"></i> Private' : ' • <i class="fas fa-globe"></i> Public') +
                    '</div>' +
                '</div>' +
                '<div class="repo-actions" style="display: flex; gap: 8px;">' +
                    (repo.is_monitored ?
                        '<button class="btn btn-sm btn-success" disabled><i class="fas fa-check"></i> Monitored</button>' :
                        '<button class="btn btn-sm btn-primary" onclick="monitorRepo(' + JSON.stringify(repo).replace(/"/g, '&quot;') + ')"><i class="fas fa-plus"></i> Add to Monitoring</button>'
                    ) +
                    (repo.repo_url ? '<a href="' + repo.repo_url + '" target="_blank" class="btn btn-sm btn-secondary"><i class="fas fa-external-link-alt"></i> View</a>' : '') +
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
            repo_name: repo.name || repo.repo_name,
            github_url: repo.repo_url || repo.html_url || `https://github.com/${repo.full_name || repo.repo_name}`
        });
        alert(`Repository ${repo.full_name || repo.repo_name} is now being monitored for drift!`);
        // Refresh the drift status to show the newly added repo
        loadDriftStatus();
        // Refresh the scan results to update monitoring statistics
        scanRepos();
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
                        '<p>Last check: ' + getLastCheckDisplay(repo.last_scan) + '</p>' +
                        '<p>Status: <a href="#" onclick="showDriftHistory(\'' + repo.repo_name + '\')" class="drift-status-link">' + getDriftStatusDisplay(repo.last_scan) + '</a></p>' +
                        '<p>Schedule: ' + (repo.schedule || 'daily') + '</p>' +
                        '<p><i class="fas fa-envelope"></i> Alerts: ' +
                            (repo.alert_email ?
                                '<span style="color: #28a745;">' + repo.alert_email + '</span>' :
                                '<span style="color: #6c757d; font-style: italic;">Not set</span>'
                            ) +
                        '</p>' +
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

    const button = event.target;
    const originalText = button.innerHTML;
    button.disabled = true;
    button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Starting...';

    try {
        const status = await API.get('/drift/status');
        const repo = status.configurations?.find(r => r.config_id === configId);

        if (!repo) {
            throw new Error('Repository configuration not found');
        }

        const result = await API.post('/terraform/execute', {
            repo_url: repo.github_url || repo.repo_url,
            branch: repo.branch || 'main',
            terraform_dir: repo.terraform_dir || '.'
        });

        if (result.error) {
            throw new Error(result.error);
        }

        if (result.success) {
            alert(`✅ Terraform scan started! Task: ${result.task_id}\n\nThe scan is running in the background. Results will appear in Plan History when complete.`);
        } else {
            throw new Error('Failed to start terraform scan');
        }

        setTimeout(() => loadDriftStatus(), 1000);

    } catch (error) {
        console.error('Drift check error:', error);
        alert(`❌ Scan failed: ${error.message}`);
    } finally {
        button.disabled = false;
        button.innerHTML = originalText;
    }
}

function showDriftConfigModal() {
    alert('Drift configuration modal - Feature coming soon!');
}

async function editDriftConfig(configId, repo) {
    if (!API.requireAuth()) return;

    const modal = document.createElement('div');
    modal.className = 'modal';
    modal.style.cssText = `
        position: fixed; top: 0; left: 0; width: 100%; height: 100%;
        background: rgba(0,0,0,0.5); z-index: 1000; display: flex;
        align-items: center; justify-content: center;
    `;

    const content = document.createElement('div');
    content.style.cssText = `
        background: white; padding: 30px; border-radius: 12px;
        max-width: 500px; width: 90%; box-shadow: 0 10px 30px rgba(0,0,0,0.3);
    `;

    content.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 25px;">
            <h3 style="margin: 0; color: #333;"><i class="fas fa-cog"></i> Edit Drift Monitoring</h3>
            <button onclick="this.closest('.modal').remove()" style="background: none; border: none; font-size: 24px; cursor: pointer; color: #666;">&times;</button>
        </div>

        <div style="margin-bottom: 20px;">
            <p style="margin: 0 0 15px 0; color: #666; font-size: 14px;">
                <i class="fab fa-github"></i> <strong>${repo.repo_name || repo.name}</strong>
            </p>
        </div>

        <div class="form-group" style="margin-bottom: 20px;">
            <label style="display: block; margin-bottom: 8px; font-weight: 500; color: #333;">
                <i class="fas fa-clock"></i> Schedule
            </label>
            <select id="edit-schedule" style="width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 6px; font-size: 14px;">
                <option value="hourly" ${(repo.schedule || 'daily') === 'hourly' ? 'selected' : ''}>Hourly</option>
                <option value="daily" ${(repo.schedule || 'daily') === 'daily' ? 'selected' : ''}>Daily</option>
            </select>
        </div>

        <div class="form-group" style="margin-bottom: 25px;">
            <label style="display: block; margin-bottom: 8px; font-weight: 500; color: #333;">
                <i class="fas fa-envelope"></i> Alert Email (optional)
            </label>
            <input type="email" id="edit-email" placeholder="Enter email for drift alerts"
                   value="${repo.alert_email || ''}"
                   style="width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 6px; font-size: 14px;">
            <small style="color: #666; font-size: 12px; margin-top: 5px; display: block;">
                Leave empty to disable email notifications
            </small>
        </div>

        <div style="display: flex; gap: 10px; justify-content: flex-end;">
            <button onclick="this.closest('.modal').remove()"
                    style="padding: 10px 20px; border: 1px solid #ddd; background: white; border-radius: 6px; cursor: pointer; color: #666;">
                Cancel
            </button>
            <button onclick="saveDriftConfig('${configId}', '${repo.repo_name || repo.name}')"
                    style="padding: 10px 20px; border: none; background: #007bff; color: white; border-radius: 6px; cursor: pointer;">
                <i class="fas fa-save"></i> Save Changes
            </button>
        </div>
    `;

    modal.appendChild(content);
    document.body.appendChild(modal);

    // Close modal when clicking outside
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            modal.remove();
        }
    });
}

async function saveDriftConfig(configId, repoName) {
    const schedule = document.getElementById('edit-schedule').value;
    const email = document.getElementById('edit-email').value.trim();

    try {
        const encodedConfigId = encodeURIComponent(configId);
        await API.put(`/drift/update/${encodedConfigId}`, {
            schedule: schedule,
            alert_email: email || null
        });

        document.querySelector('.modal').remove();
        alert(`Repository ${repoName} configuration updated successfully!`);
        loadDriftStatus(); // Refresh status
        scanRepos(); // Refresh scan results
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
        scanRepos(); // Refresh scan results to update monitoring statistics
    } catch (error) {
        alert(`Failed to delete repository: ${error.message}`);
    }
}



function getLastCheckDisplay(lastScan) {
    if (!lastScan || !lastScan.timestamp) {
        return 'Not yet scanned';
    }

    // Check if scan is older than 7 days from when monitoring was likely set up
    const scanDate = new Date(lastScan.timestamp);
    const now = new Date();
    const daysDiff = (now - scanDate) / (1000 * 60 * 60 * 24);

    // If scan is more than 7 days old, treat as "not yet scanned" for monitoring purposes
    if (daysDiff > 7) {
        return 'Not yet scanned';
    }

    // Format recent timestamp nicely
    return new Date(lastScan.timestamp).toLocaleString();
}

function getDriftStatusDisplay(lastScan) {
    if (!lastScan) {
        return '⏳ Not scanned yet';
    }

    // Check status field first (most reliable)
    if (lastScan.status === 'error') {
        return '❌ Error';
    }

    // Check for error in plan_content as fallback
    if (lastScan.plan_content && (lastScan.plan_content.includes('error') || lastScan.plan_content.includes('Error') || lastScan.plan_content.includes('failed'))) {
        return '❌ Error';
    }

    if (lastScan.drift_detected) {
        return '⚠️ Drift detected';
    }

    return '✅ No drift';
}

async function showDriftHistory(repoName) {
    if (!API.requireAuth()) return;

    try {
        const history = await API.get(`/plan-history/${encodeURIComponent(repoName)}`);
        displayDriftHistoryModal(repoName, history.plans || []);
    } catch (error) {
        alert(`Failed to load drift history: ${error.message}`);
    }
}

function displayDriftHistoryModal(repoName, plans) {
    const modal = document.createElement('div');
    modal.className = 'modal';
    modal.style.cssText = `
        position: fixed; top: 0; left: 0; width: 100%; height: 100%;
        background: rgba(0,0,0,0.5); z-index: 1000; display: flex;
        align-items: center; justify-content: center;
    `;

    const content = document.createElement('div');
    content.style.cssText = `
        background: white; padding: 20px; border-radius: 8px;
        max-width: 80%; max-height: 80%; overflow-y: auto;
        min-width: 600px;
    `;

    content.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
            <h3>Drift History: ${repoName}</h3>
            <button onclick="this.closest('.modal').remove()" style="background: none; border: none; font-size: 24px; cursor: pointer;">&times;</button>
        </div>
        <div class="drift-history-list">
            ${plans.length === 0 ? '<p>No scan history found.</p>' :
                plans.map(plan => `
                    <div class="drift-history-item" style="border: 1px solid #ddd; padding: 15px; margin-bottom: 10px; border-radius: 4px;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                            <strong>${new Date(plan.timestamp).toLocaleString()}</strong>
                            <span class="status-badge ${getStatusClass(plan)}">${getStatusText(plan)}</span>
                        </div>
                        <div style="margin-bottom: 10px;">
                            <strong>Changes:</strong> ${plan.changes_detected || 0}
                        </div>
                        <details>
                            <summary style="cursor: pointer; color: #007bff;">View Details</summary>
                            <pre style="background: #f8f9fa; padding: 10px; margin-top: 10px; border-radius: 4px; overflow-x: auto; white-space: pre-wrap;">${plan.plan_content || 'No plan content found in database'}</pre>
                            ${!plan.plan_content ? `<div style="margin-top: 10px; padding: 10px; background: #fff3cd; border: 1px solid #ffeaa7; border-radius: 4px;"><strong>Debug Info:</strong><br>Plan ID: ${plan.plan_id || 'Unknown'}<br>Status: ${plan.status || 'Unknown'}<br>Drift Detected: ${plan.drift_detected || false}<br>Timestamp: ${plan.timestamp || 'Unknown'}</div>` : ''}
                        </details>
                    </div>
                `).join('')
            }
        </div>
    `;

    modal.appendChild(content);
    document.body.appendChild(modal);

    // Close modal when clicking outside
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            modal.remove();
        }
    });
}

function getStatusClass(plan) {
    // Check status field first
    if (plan.status === 'error') {
        return 'error';
    }

    // Check for error in plan_content as fallback
    if (plan.plan_content && (plan.plan_content.includes('error') || plan.plan_content.includes('Error') || plan.plan_content.includes('failed'))) {
        return 'error';
    }

    // Only show drift if not an error
    if (plan.drift_detected && plan.status !== 'error') {
        return 'drift';
    }

    return 'no-drift';
}

function getStatusText(plan) {
    // Check status field first
    if (plan.status === 'error') {
        return '❌ Error';
    }

    // Check for error in plan_content as fallback
    if (plan.plan_content && (plan.plan_content.includes('error') || plan.plan_content.includes('Error') || plan.plan_content.includes('failed'))) {
        return '❌ Error';
    }

    // Only show drift if not an error
    if (plan.drift_detected && plan.status !== 'error') {
        return '⚠️ Drift';
    }

    return '✅ No Drift';
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
