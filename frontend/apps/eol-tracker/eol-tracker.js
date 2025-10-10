// EOL Tracker App Module

function initializeEOLTracker() {
    // Initialize any default state
}

async function runEOLScan() {
    if (!API.requireAuth()) return;

    const githubTarget = document.getElementById('github-target').value.trim();
    if (!githubTarget) {
        alert('Please enter a GitHub target (username/org or username/repo)');
        return;
    }

    const githubToken = document.getElementById('github-token').value.trim();

    const button = event.target.closest('button');
    const originalText = button.innerHTML;
    button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Scanning...';
    button.disabled = true;

    try {
        const requestData = {
            github_target: githubTarget
        };

        if (githubToken) {
            requestData.github_token = githubToken;
        }

        const result = await API.post('/eol/scan', requestData);
        displayEOLScanResults(result);
    } catch (error) {
        document.getElementById('eol-results').innerHTML = `<p>Scan failed: ${error.message}</p>`;
    } finally {
        button.innerHTML = originalText;
        button.disabled = false;
    }
}

function displayEOLScanResults(result) {
    const container = document.getElementById('eol-results');

    if (!result.scan_results || result.scan_results.length === 0) {
        container.innerHTML = '<p>No repositories found or no technologies detected! 🎉</p>';
        return;
    }

    // Create summary
    const summaryHTML = `
        <div class="scan-summary">
            <h4>Scan Results Summary</h4>
            <p><strong>Repositories Scanned:</strong> ${result.scanned_repos}</p>
            <p><strong>Total Technologies:</strong> ${result.total_technologies}</p>
        </div>
    `;

    // Collect all technologies from all repos
    const allTechnologies = [];
    const repoNames = new Set();

    result.scan_results.forEach(repo => {
        repoNames.add(repo.repo_name);
        if (repo.technologies) {
            repo.technologies.forEach(tech => {
                allTechnologies.push({
                    ...tech,
                    repository: repo.repo_name
                });
            });
        }
    });

    populateEOLRepoFilter(repoNames);

    if (allTechnologies.length === 0) {
        container.innerHTML = summaryHTML + '<p>No technologies with EOL data found! 🎉</p>';
        return;
    }

    const tableHTML = `
        <table class="eol-table">
            <thead>
                <tr>
                    <th>Technology</th>
                    <th>Version</th>
                    <th>Type</th>
                    <th>EOL Date</th>
                    <th>Repository</th>
                    <th>Risk Level</th>
                    <th>File Path</th>
                </tr>
            </thead>
            <tbody>
                ${allTechnologies.map(tech => `
                    <tr class="technology-row ${tech.risk_level || 'unknown'}" data-risk="${tech.risk_level || 'unknown'}">
                        <td><strong>${tech.technology || tech.name || 'Unknown'}</strong></td>
                        <td>${tech.version || 'Unknown'}</td>
                        <td>${tech.tech_type || 'Unknown'}</td>
                        <td>${formatDate(tech.eol_date)}</td>
                        <td>${tech.repository || 'N/A'}</td>
                        <td><span class="finding ${tech.risk_level || 'unknown'}">${(tech.risk_level || 'unknown').toUpperCase()}</span></td>
                        <td>${tech.file_path ? `<a href="${tech.github_url || '#'}" target="_blank">${tech.file_path}</a>` : 'N/A'}</td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;

    container.innerHTML = summaryHTML + tableHTML;
    setupEOLTableFilters();
}

function displayEOLResults(technologies) {
    // Legacy function - redirect to new function
    displayEOLScanResults({ scan_results: [{ repo_name: 'Legacy', technologies: technologies }], scanned_repos: 1, total_technologies: technologies.length });
}

function populateEOLRepoFilter(repoNames) {
    const filter = document.getElementById('eol-repo-filter');

    // Clear existing options except "All Repositories"
    filter.innerHTML = '<option value="all">All Repositories</option>';

    // Add repository options
    repoNames.forEach(repo => {
        const option = document.createElement('option');
        option.value = repo;
        option.textContent = repo;
        filter.appendChild(option);
    });
}

function setupEOLTableFilters() {
    const searchFilter = document.getElementById('eol-search-filter');
    const riskFilter = document.getElementById('eol-risk-filter');
    const repoFilter = document.getElementById('eol-repo-filter');

    function filterTable() {
        const searchTerm = searchFilter.value.toLowerCase();
        const riskLevel = riskFilter.value;
        const repository = repoFilter.value;

        const rows = document.querySelectorAll('.technology-row');

        rows.forEach(row => {
            const techName = row.cells[0].textContent.toLowerCase();
            const techRisk = row.dataset.risk;
            const techRepo = row.cells[3].textContent;

            const matchesSearch = techName.includes(searchTerm);
            const matchesRisk = riskLevel === 'all' || techRisk === riskLevel;
            const matchesRepo = repository === 'all' || techRepo === repository;

            row.style.display = matchesSearch && matchesRisk && matchesRepo ? '' : 'none';
        });
    }

    searchFilter.addEventListener('input', filterTable);
    riskFilter.addEventListener('change', filterTable);
    repoFilter.addEventListener('change', filterTable);
}

function formatDate(dateString) {
    if (!dateString) return 'Unknown';

    try {
        const date = new Date(dateString);
        return date.toLocaleDateString();
    } catch (error) {
        return dateString;
    }
}
