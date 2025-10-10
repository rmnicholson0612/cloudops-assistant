// Drift Detection App Module

function initializeDriftDetection() {
    autoPopulateGitHubForm();
    loadDriftStatus();
    loadAIExplanations();

    // Auto-scan if GitHub target is pre-configured
    const githubTargetInput = document.getElementById('github-target');
    if (githubTargetInput && githubTargetInput.value.trim()) {
        // Small delay to ensure UI is ready
        setTimeout(() => {
            scanRepos();
        }, 500);
    }
}

// AI Terraform Explainer functionality
async function loadAIExplanations() {
    const display = document.getElementById('ai-explanations-display');
    if (!display) return;

    display.innerHTML = '<div class="ai-loading"><i class="fas fa-spinner fa-spin"></i> Loading AI explanations...</div>';

    try {
        console.log('Fetching AI explanations...');
        const response = await API.get('/ai/explanations');
        console.log('AI explanations response:', response);

        if (response && response.explanations && response.explanations.length > 0) {
            display.innerHTML = response.explanations.map(exp => {
                const explanation = exp.ai_explanation || exp.explanation || {};
                return `
                    <div class="explanation-item">
                        <h4>${exp.repo_name || 'Terraform Plan'}</h4>
                        <div class="explanation-content">${explanation.summary || 'No explanation available'}</div>
                        <div class="explanation-meta">
                            <span class="risk-level risk-${(explanation.risk_level || 'unknown').toLowerCase()}">${explanation.risk_level || 'Unknown'}</span>
                            <span class="timestamp">${new Date(exp.ai_analyzed_at || exp.timestamp).toLocaleString()}</span>
                        </div>
                    </div>
                `;
            }).join('');
        } else {
            display.innerHTML = '<div class="no-data"><i class="fas fa-info-circle"></i> No AI explanations available yet.<br><br>To get AI insights:<br>1. Upload terraform plans using the repository scanning above<br>2. Use the "Explain with AI" feature on uploaded plans<br>3. AI explanations will appear here</div>';
        }
    } catch (error) {
        console.error('Error loading AI explanations:', error);
        display.innerHTML = `<div class="error"><i class="fas fa-exclamation-triangle"></i> Failed to load AI explanations<br><small>Error: ${error.message || 'Unknown error'}</small></div>`;
    }
}

// Repository scanning functionality
async function scanRepos() {
    const githubTarget = document.getElementById('github-target').value.trim();
    const githubToken = document.getElementById('github-token').value.trim();
    const resultsElement = document.getElementById('scan-results');

    if (!githubTarget) {
        resultsElement.innerHTML = '<div class="error"><i class="fas fa-exclamation-circle"></i> Please enter a GitHub username or organization</div>';
        return;
    }

    if (!API.isAuthenticated()) {
        resultsElement.innerHTML = '<div class="error"><i class="fas fa-lock"></i> Please login to scan repositories</div>';
        return;
    }

    resultsElement.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Scanning repositories...';

    try {
        const response = await API.post('/scan-repos', {
            github_target: githubTarget,
            github_token: githubToken || null
        });

        displayScanResults(response);
    } catch (error) {
        resultsElement.innerHTML = `<div class="error">
            <i class="fas fa-times-circle"></i> <strong>Error scanning repositories</strong>
            <p>${error.message || 'Unknown error occurred'}</p>
        </div>`;
    }
}

function displayScanResults(data) {
    const resultsElement = document.getElementById('scan-results');

    if (data.terraform_repos === 0) {
        resultsElement.innerHTML = `<div class="no-drift">
            <i class="fas fa-info-circle"></i> <strong>No Terraform repositories found</strong>
            <p>Scanned ${data.total_repos} repositories for ${data.target}, but none contain Terraform files.</p>
        </div>`;
        return;
    }

    // Calculate monitoring coverage
    const monitoredCount = data.monitored_repos || 0;
    const coveragePercentage = data.coverage_percentage || 0;

    let html = `<div class="scan-summary">
        <h4>Scan Results for ${data.target}</h4>
        <div class="scan-stats">
            <div class="stat-item">
                <span class="stat-number">${data.terraform_repos}</span>
                <span class="stat-label">Terraform repos</span>
            </div>
            <div class="stat-item">
                <span class="stat-number">${data.total_repos}</span>
                <span class="stat-label">Total repos</span>
            </div>
            <div class="stat-item">
                <span class="stat-number">${monitoredCount}</span>
                <span class="stat-label">Monitored</span>
            </div>
            <div class="stat-item">
                <span class="stat-number">${coveragePercentage}%</span>
                <span class="stat-label">Coverage</span>
            </div>
        </div>
    </div>`;

    html += '<div class="repo-results">';

    data.results.forEach(repo => {
        const isMonitored = repo.is_monitored || false;
        const monitoringStatus = isMonitored ? 'Monitored' : 'Not monitored';
        const monitoringClass = isMonitored ? 'monitored' : 'not-monitored';

        html += `<div class="repo-item ${monitoringClass}">
            <div class="repo-header">
                <i class="fab fa-github" style="color: #333;"></i>
                <strong><a href="${repo.repo_url}" target="_blank">${repo.repo_name}</a></strong>
                <span class="status">${monitoringStatus}</span>
                ${repo.private ? '<span class="private-badge"><i class="fas fa-lock"></i> Private</span>' : ''}
                <div class="repo-actions">
                    <button class="btn btn-secondary btn-sm" onclick="viewRepoHistory('${repo.repo_name}', '${data.target}')">
                        <i class="fas fa-history"></i> View
                    </button>
                    ${isMonitored ?
                        `<button class="btn btn-warning btn-sm" onclick="removeFromMonitoring('${repo.repo_name}')">
                            <i class="fas fa-minus"></i> Remove
                        </button>` :
                        `<button class="btn btn-success btn-sm" onclick="addToMonitoring('${repo.repo_name}', '${repo.repo_url}', '${data.target}')">
                            <i class="fas fa-plus"></i> Add to Monitoring
                        </button>`
                    }
                </div>
            </div>
        </div>`;
    });

    html += '</div>';
    resultsElement.innerHTML = html;
}

// Plan upload functionality
let currentRepo = null;
let currentTarget = null;

function showUploadModal(repoName, githubTarget) {
    currentRepo = repoName;
    currentTarget = githubTarget;
    document.getElementById('upload-repo-name').textContent = repoName;
    document.getElementById('upload-modal').style.display = 'block';
    document.getElementById('upload-result').innerHTML = '';
}

function closeUploadModal() {
    document.getElementById('upload-modal').style.display = 'none';
    document.getElementById('plan-file').value = '';
    document.getElementById('upload-btn').disabled = true;
}

async function uploadPlan() {
    const fileInput = document.getElementById('plan-file');
    const file = fileInput.files[0];
    const resultElement = document.getElementById('upload-result');

    if (!file) {
        resultElement.innerHTML = '<div class="error">Please select a file first</div>';
        return;
    }

    resultElement.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processing terraform plan...';
    document.getElementById('upload-btn').disabled = true;

    try {
        const planContent = await file.text();

        const response = await API.post('/upload-plan', {
            repo_name: currentRepo,
            github_target: currentTarget,
            plan_content: planContent
        });

        displayPlanResult(response);
    } catch (error) {
        resultElement.innerHTML = `<div class="error">
            <i class="fas fa-times-circle"></i> <strong>Error processing plan</strong>
            <p>${error.message || 'Unknown error occurred'}</p>
        </div>`;
    } finally {
        document.getElementById('upload-btn').disabled = false;
    }
}

function displayPlanResult(data) {
    const resultElement = document.getElementById('upload-result');

    if (data.drift_detected) {
        let html = `<div class="drift-detected">
            <i class="fas fa-exclamation-triangle"></i> <strong>Drift Detected!</strong>
            <p>Found ${data.total_changes} changes in your infrastructure</p>
        </div>`;

        if (data.changes.length > 0) {
            html += '<div class="drift-details">';
            data.changes.forEach(change => {
                html += `<div class="drift-item">${change}</div>`;
            });
            if (data.total_changes > data.changes.length) {
                html += `<div class="drift-item">... and ${data.total_changes - data.changes.length} more changes</div>`;
            }
            html += '</div>';
        }

        resultElement.innerHTML = html;
    } else {
        resultElement.innerHTML = `<div class="no-drift">
            <i class="fas fa-check-circle"></i> <strong>No drift detected!</strong>
            <p>Your infrastructure matches the terraform configuration.</p>
        </div>`;
    }
}

// Drift monitoring functions
async function loadDriftStatus() {
    const displayElement = document.getElementById('drift-status-display');
    if (!displayElement) return;

    if (!API.isAuthenticated()) {
        displayElement.innerHTML = '<div class="drift-error"><i class="fas fa-lock"></i> Please login to view drift status</div>';
        return;
    }

    displayElement.innerHTML = '<div class="drift-loading"><i class="fas fa-spinner fa-spin"></i> Loading drift monitoring status...</div>';

    try {
        const response = await API.get('/drift/status');

        if (response.configurations.length === 0) {
            displayElement.innerHTML = '<div class="no-drift-config">No repositories configured for drift monitoring</div>';
            return;
        }

        displayDriftStatus(response.configurations);
    } catch (error) {
        displayElement.innerHTML = `<div class="drift-error">
            <i class="fas fa-exclamation-triangle"></i> Error loading drift status: ${error.message}
        </div>`;
    }
}

function displayDriftStatus(configurations) {
    const displayElement = document.getElementById('drift-status-display');

    let html = '<div class="drift-config-list">';
    configurations.forEach(config => {
        const lastScan = config.last_scan ? new Date(config.last_scan.timestamp).toLocaleString() : 'Never';
        const driftStatus = config.last_scan?.drift_detected ? 'Drift Detected' : 'No Drift';
        const statusClass = config.last_scan?.drift_detected ? 'has-drift' : 'no-drift';

        html += `
            <div class="drift-config-item ${statusClass}">
                <div class="drift-config-info">
                    <div class="drift-repo-name">${config.repo_name}</div>
                    <div class="drift-schedule">Schedule: ${config.schedule}</div>
                    <div class="drift-last-scan">Last scan: ${lastScan}</div>
                    <div class="drift-alert-email">Alert email: ${config.alert_email || 'unset'}</div>
                    <div class="drift-status">${driftStatus}</div>
                </div>
                <div class="drift-config-actions">
                    <button class="btn btn-sm btn-primary" onclick="runManualScan('${config.config_id}')" title="Run manual scan">
                        <i class="fas fa-play"></i>
                    </button>
                    <button class="btn btn-sm btn-secondary" onclick="viewLastScan('${config.repo_name}')" title="View last scan">
                        <i class="fas fa-eye"></i>
                    </button>
                    <button class="btn btn-sm btn-warning" onclick="editDriftConfig('${config.config_id}', '${config.repo_name}', '${config.schedule}', '${config.alert_email || ''}')" title="Edit configuration">
                        <i class="fas fa-edit"></i>
                    </button>
                    <button class="btn btn-sm btn-danger" onclick="deleteDriftConfig('${config.config_id}')">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>`;
    });
    html += '</div>';

    displayElement.innerHTML = html;
}

// Auto-populate GitHub form fields from config
function autoPopulateGitHubForm() {
    const githubTargetInput = document.getElementById('github-target');
    const githubTokenInput = document.getElementById('github-token');

    if (!githubTargetInput || !githubTokenInput) return;

    // Auto-populate target if configured
    if (CONFIG.GITHUB_DEFAULT_TARGET && CONFIG.GITHUB_DEFAULT_TARGET.trim() !== '') {
        githubTargetInput.value = CONFIG.GITHUB_DEFAULT_TARGET;
        githubTargetInput.style.backgroundColor = '#e8f5e8'; // Light green to show it's pre-filled
    }

    // Auto-populate token if configured
    if (CONFIG.GITHUB_DEFAULT_TOKEN && CONFIG.GITHUB_DEFAULT_TOKEN.trim() !== '') {
        githubTokenInput.value = CONFIG.GITHUB_DEFAULT_TOKEN;
        githubTokenInput.style.backgroundColor = '#e8f5e8'; // Light green to show it's pre-filled
    }
}

// Clear GitHub form fields
function clearGitHubForm() {
    const githubTargetInput = document.getElementById('github-target');
    const githubTokenInput = document.getElementById('github-token');

    githubTargetInput.value = '';
    githubTokenInput.value = '';
    githubTargetInput.style.backgroundColor = '';
    githubTokenInput.style.backgroundColor = '';

    // Clear scan results
    document.getElementById('scan-results').innerHTML = 'Enter a GitHub username or organization to scan for terraform repositories...';
}

// File selection handling
document.addEventListener('DOMContentLoaded', function() {
    const fileInput = document.getElementById('plan-file');
    if (fileInput) {
        fileInput.addEventListener('change', function(e) {
            const file = e.target.files[0];
            if (file) {
                document.querySelector('.file-drop-zone p').textContent = `Selected: ${file.name}`;
                document.getElementById('upload-btn').disabled = false;
            }
        });
    }

    // Add CSS for live status modal
    const style = document.createElement('style');
    style.textContent = `
        .status-timeline {
            max-height: 300px;
            overflow-y: auto;
            margin: 20px 0;
            border: 1px solid #ddd;
            border-radius: 8px;
            padding: 15px;
            background: #f9f9f9;
        }
        .status-item {
            display: flex;
            align-items: flex-start;
            margin-bottom: 15px;
            padding: 10px;
            border-radius: 6px;
            background: white;
            border-left: 4px solid #ddd;
        }
        .status-item.active {
            border-left-color: #007bff;
            box-shadow: 0 2px 4px rgba(0,123,255,0.1);
        }
        .status-item.completed {
            border-left-color: #28a745;
        }
        .status-item.failed {
            border-left-color: #dc3545;
            background: #fff5f5;
        }
        .status-icon {
            font-size: 20px;
            margin-right: 12px;
            min-width: 30px;
        }
        .status-content {
            flex: 1;
        }
        .status-title {
            font-weight: bold;
            color: #333;
            margin-bottom: 4px;
        }
        .status-message {
            color: #666;
            font-size: 14px;
            margin-bottom: 4px;
        }
        .status-time {
            color: #999;
            font-size: 12px;
        }
        .progress-bar {
            width: 100%;
            height: 8px;
            background: #e9ecef;
            border-radius: 4px;
            overflow: hidden;
            margin: 15px 0;
        }
        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #007bff, #0056b3);
            transition: width 0.5s ease;
            border-radius: 4px;
        }
        .progress-fill.error {
            background: linear-gradient(90deg, #dc3545, #c82333);
        }
        .task-info {
            background: #f8f9fa;
            padding: 10px;
            border-radius: 6px;
            margin-bottom: 15px;
            font-family: monospace;
        }
    `;
    document.head.appendChild(style);
});

// Repository monitoring functions
async function viewRepoHistory(repoName, githubTarget) {
    if (!API.isAuthenticated()) {
        alert('Please login to view repository history');
        return;
    }

    try {
        const response = await API.get(`/plan-history/${encodeURIComponent(repoName)}`);

        if (response.plans && response.plans.length > 0) {
            // Show history in a modal or alert for now
            let historyText = `Plan History for ${repoName}:\n\n`;
            response.plans.slice(0, 5).forEach((plan, index) => {
                const date = new Date(plan.timestamp).toLocaleString();
                const status = plan.drift_detected ? 'DRIFT DETECTED' : 'No drift';
                historyText += `${index + 1}. ${date} - ${status}\n`;
            });

            if (response.plans.length > 5) {
                historyText += `\n... and ${response.plans.length - 5} more plans`;
            }

            alert(historyText);
        } else {
            alert(`No plan history found for ${repoName}`);
        }
    } catch (error) {
        alert(`Failed to load history for ${repoName}: ${error.message}`);
    }
}

async function addToMonitoring(repoName, repoUrl, githubTarget) {
    if (!API.isAuthenticated()) {
        alert('Please login to add repositories to monitoring');
        return;
    }

    const confirmed = confirm(`Add ${repoName} to scheduled drift monitoring?\n\nThis will enable automatic terraform plan execution and drift detection.`);
    if (!confirmed) return;

    try {
        const response = await API.post('/drift/configure', {
            repo_name: repoName,
            github_url: repoUrl,
            schedule: 'daily',
            alert_email: null
        });

        alert(`Successfully added ${repoName} to drift monitoring!`);

        // Refresh the scan results to show updated monitoring status
        await scanRepos();

        // Also refresh the drift status section
        await loadDriftStatus();
    } catch (error) {
        alert(`Failed to add ${repoName} to monitoring: ${error.message}`);
    }
}

async function removeFromMonitoring(repoName) {
    if (!API.isAuthenticated()) {
        alert('Please login to manage monitoring');
        return;
    }

    const confirmed = confirm(`Remove ${repoName} from scheduled drift monitoring?\n\nThis will stop automatic drift detection for this repository.`);
    if (!confirmed) return;

    try {
        // First get the config ID for this repo
        const statusResponse = await API.get('/drift/status');

        // Try multiple name variations to find the config
        const githubTarget = document.getElementById('github-target').value.trim();
        const possibleNames = [
            repoName,                           // "example-terraform"
            `${githubTarget}/${repoName}`,      // "rmnicholson0612/example-terraform"
            `${githubTarget}${repoName}`        // "rmnicholson0612example-terraform"
        ];

        let config = null;
        for (const name of possibleNames) {
            config = statusResponse.configurations.find(c => c.repo_name === name);
            if (config) break;
        }

        if (!config) {
            alert(`Configuration not found for ${repoName}`);
            return;
        }

        await API.delete(`/drift/delete/${encodeURIComponent(config.config_id)}`);

        alert(`Successfully removed ${repoName} from drift monitoring!`);

        // Refresh the scan results to show updated monitoring status
        await scanRepos();

        // Also refresh the drift status section
        await loadDriftStatus();
    } catch (error) {
        alert(`Failed to remove ${repoName} from monitoring: ${error.message}`);
    }
}

async function runManualScan(configId) {
    if (!API.isAuthenticated()) {
        alert('Please login to run manual scans');
        return;
    }

    const confirmed = confirm('Run manual terraform scan now?\n\nThis will execute terraform plan on the repository and may take 2-5 minutes.');
    if (!confirmed) return;

    try {
        const response = await API.post(`/drift/scan/${encodeURIComponent(configId)}`);

        if (response.task_id) {
            // Show live status modal
            showLiveStatusModal(response.task_id, response.message || 'Terraform scan started');
        } else {
            alert('✅ Manual scan started successfully!');
        }

        // Refresh drift status to show scan is running
        await loadDriftStatus();
    } catch (error) {
        alert(`❌ Failed to start manual scan: ${error.message}`);
    }
}

function showLiveStatusModal(taskId, initialMessage) {
    // Create modal HTML
    const modalHtml = `
        <div id="live-status-modal" class="modal" style="display: block;">
            <div class="modal-content" style="max-width: 600px;">
                <div class="modal-header">
                    <h3>🚀 Terraform Execution Status</h3>
                    <span class="close" onclick="closeLiveStatusModal()">&times;</span>
                </div>
                <div class="modal-body">
                    <div class="task-info">
                        <strong>Task ID:</strong> <code>${taskId}</code>
                    </div>
                    <div class="status-timeline" id="status-timeline">
                        <div class="status-item active">
                            <div class="status-icon">⏳</div>
                            <div class="status-content">
                                <div class="status-title">Queued</div>
                                <div class="status-message">${initialMessage}</div>
                                <div class="status-time">${new Date().toLocaleTimeString()}</div>
                            </div>
                        </div>
                    </div>
                    <div class="progress-bar">
                        <div class="progress-fill" id="progress-fill" style="width: 10%;"></div>
                    </div>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-secondary" onclick="closeLiveStatusModal()">Close</button>
                </div>
            </div>
        </div>
    `;

    // Add modal to page
    document.body.insertAdjacentHTML('beforeend', modalHtml);

    // Start polling for status updates
    pollForTaskStatus(taskId);
}

function closeLiveStatusModal() {
    const modal = document.getElementById('live-status-modal');
    if (modal) {
        modal.remove();
    }
    // Clear any active polling
    if (window.statusPollInterval) {
        clearInterval(window.statusPollInterval);
        window.statusPollInterval = null;
    }
}

function pollForTaskStatus(taskId) {
    let pollCount = 0;
    const maxPolls = 40; // 20 minutes max

    window.statusPollInterval = setInterval(async () => {
        pollCount++;

        try {
            const status = await API.get(`/drift/task-status/${taskId}`);
            updateStatusTimeline(status);

            // Stop polling if task is complete or failed
            if (status.status === 'completed' || status.status === 'failed') {
                clearInterval(window.statusPollInterval);
                window.statusPollInterval = null;

                // Refresh drift status after completion
                setTimeout(() => {
                    loadDriftStatus();
                }, 2000);
            }

            if (pollCount >= maxPolls) {
                clearInterval(window.statusPollInterval);
                window.statusPollInterval = null;
                addStatusItem('timeout', 'Timeout', 'Stopped polling after 20 minutes', false);
            }
        } catch (error) {
            console.error('Error polling task status:', error);
            addStatusItem('error', 'Error', `Failed to get status: ${error.message}`, false);
        }
    }, 30000); // Poll every 30 seconds

    // Also poll immediately
    setTimeout(async () => {
        try {
            const status = await API.get(`/drift/task-status/${taskId}`);
            updateStatusTimeline(status);
        } catch (error) {
            console.error('Error getting initial status:', error);
        }
    }, 2000);
}

function updateStatusTimeline(status) {
    const statusMap = {
        'queued': { icon: '⏳', title: 'Queued', progress: 10 },
        'starting': { icon: '🚀', title: 'Starting', progress: 20 },
        'cloning': { icon: '📥', title: 'Cloning Repository', progress: 40 },
        'analyzing': { icon: '🔍', title: 'Analyzing Files', progress: 60 },
        'planning': { icon: '📋', title: 'Running Terraform Plan', progress: 80 },
        'completed': { icon: '✅', title: 'Completed', progress: 100 },
        'failed': { icon: '❌', title: 'Failed', progress: 100 }
    };

    const statusInfo = statusMap[status.status] || { icon: '❓', title: status.status, progress: 50 };

    // Update progress bar
    const progressFill = document.getElementById('progress-fill');
    if (progressFill) {
        progressFill.style.width = `${statusInfo.progress}%`;
        progressFill.className = `progress-fill ${status.status === 'failed' ? 'error' : ''}`;
    }

    // Add new status item if it's different from the last one
    const timeline = document.getElementById('status-timeline');
    const lastItem = timeline?.querySelector('.status-item:last-child');
    const lastStatus = lastItem?.querySelector('.status-title')?.textContent;

    if (lastStatus !== statusInfo.title) {
        addStatusItem(status.status, statusInfo.title, status.message, true, statusInfo.icon);
    }
}

function addStatusItem(status, title, message, isActive, icon = '📋') {
    const timeline = document.getElementById('status-timeline');
    if (!timeline) return;

    // Deactivate previous items
    timeline.querySelectorAll('.status-item').forEach(item => {
        item.classList.remove('active');
    });

    const statusItem = document.createElement('div');
    statusItem.className = `status-item ${isActive ? 'active' : ''} ${status}`;
    statusItem.innerHTML = `
        <div class="status-icon">${icon}</div>
        <div class="status-content">
            <div class="status-title">${title}</div>
            <div class="status-message">${message}</div>
            <div class="status-time">${new Date().toLocaleTimeString()}</div>
        </div>
    `;

    timeline.appendChild(statusItem);

    // Scroll to bottom
    statusItem.scrollIntoView({ behavior: 'smooth' });
}

async function viewLastScan(repoName) {
    if (!API.isAuthenticated()) {
        alert('Please login to view scan history');
        return;
    }

    try {
        const response = await API.get(`/plan-history/${encodeURIComponent(repoName)}`);

        if (response.plans && response.plans.length > 0) {
            const latestPlan = response.plans[0];
            const date = new Date(latestPlan.timestamp).toLocaleString();
            const status = latestPlan.drift_detected ? '⚠️ DRIFT DETECTED' : '✅ No drift';

            alert(`Latest scan for ${repoName}:\n\n` +
                  `Date: ${date}\n` +
                  `Status: ${status}\n` +
                  `Changes: ${latestPlan.changes_detected || 0}\n\n` +
                  `${latestPlan.plan_content ? latestPlan.plan_content.substring(0, 500) + '...' : 'No plan content available'}`);
        } else {
            alert(`No scan history found for ${repoName}`);
        }
    } catch (error) {
        alert(`Failed to load scan history: ${error.message}`);
    }
}

function editDriftConfig(configId, repoName, schedule, email) {
    alert(`Edit drift config for ${repoName} - Feature needs full implementation`);
}

async function deleteDriftConfig(configId) {
    if (!API.isAuthenticated()) {
        alert('Please login to delete configurations');
        return;
    }

    if (!confirm('Are you sure you want to delete this drift configuration?\n\nThis will also delete all historical scan data for this repository.')) {
        return;
    }

    try {
        await API.delete(`/drift/delete/${encodeURIComponent(configId)}`);
        alert('Configuration deleted successfully!');

        // Refresh the drift status display
        await loadDriftStatus();

        // Also refresh scan results if they're visible
        const githubTargetInput = document.getElementById('github-target');
        if (githubTargetInput && githubTargetInput.value.trim()) {
            await scanRepos();
        }
    } catch (error) {
        alert(`Failed to delete configuration: ${error.message}`);
    }
}
