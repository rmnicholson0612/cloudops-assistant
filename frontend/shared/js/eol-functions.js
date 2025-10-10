// EOL Tracker Functions - Missing functions for repository dropdown

function setupEOLTableFilters() {
    const searchFilter = document.getElementById('eol-search-filter');
    const riskFilter = document.getElementById('eol-risk-filter');
    const repoFilter = document.getElementById('eol-repo-filter');

    if (!searchFilter || !riskFilter || !repoFilter) return;

    // Add event listeners for filtering
    [searchFilter, riskFilter, repoFilter].forEach(filter => {
        filter.addEventListener('input', filterEOLTable);
        filter.addEventListener('change', filterEOLTable);
    });
}

function populateEOLRepoFilter(repoNames) {
    const repoFilter = document.getElementById('eol-repo-filter');
    if (!repoFilter) return;

    // Clear existing options except "All Repositories"
    repoFilter.innerHTML = '<option value="all">All Repositories</option>';

    // Add repository options
    Array.from(repoNames).sort().forEach(repoName => {
        const option = document.createElement('option');
        option.value = repoName;
        option.textContent = repoName;
        repoFilter.appendChild(option);
    });
}

function filterEOLTable() {
    const searchTerm = document.getElementById('eol-search-filter').value.toLowerCase();
    const riskLevel = document.getElementById('eol-risk-filter').value;
    const repoName = document.getElementById('eol-repo-filter').value;

    const rows = document.querySelectorAll('.technology-row');

    rows.forEach(row => {
        const technology = row.cells[0].textContent.toLowerCase();
        const repository = row.cells[3].textContent;
        const risk = row.dataset.risk || 'unknown';

        let show = true;

        // Search filter
        if (searchTerm && !technology.includes(searchTerm)) {
            show = false;
        }

        // Risk filter
        if (riskLevel !== 'all' && risk !== riskLevel) {
            show = false;
        }

        // Repository filter
        if (repoName !== 'all' && repository !== repoName) {
            show = false;
        }

        row.style.display = show ? '' : 'none';
    });
}

// Helper function to format dates
function formatDate(dateString) {
    if (!dateString) return 'N/A';
    try {
        return new Date(dateString).toLocaleDateString();
    } catch (e) {
        return dateString;
    }
}
