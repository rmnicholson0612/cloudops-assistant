// Service Documentation App Module
console.log('Service Documentation script loaded');

function initializeServiceDocs() {
    console.log('Service Documentation initialized');
}

async function loadServices() {
    const display = document.getElementById('services-display');
    if (!display) return;

    display.innerHTML = '<div class="loading"><i class="fas fa-spinner fa-spin"></i> Loading services...</div>';

    try {
        const response = await API.get('/docs/services');
        if (response.services && response.services.length > 0) {
            display.innerHTML = response.services.map(service => `
                <div class="service-item">
                    <div class="service-header">
                        <h4>${service.service_name}</h4>
                        <span class="doc-count">${service.doc_count || 0} docs</span>
                    </div>
                    <div class="service-meta">
                        <span><i class="fas fa-user"></i> ${service.owner || 'Unknown'}</span>
                        <span><i class="fab fa-github"></i> ${service.github_repo || 'No repo'}</span>
                        <span><i class="fas fa-clock"></i> ${new Date(service.updated_at).toLocaleDateString()}</span>
                    </div>
                </div>
            `).join('');
        } else {
            display.innerHTML = '<div class="no-results"><i class="fas fa-info-circle"></i> No services registered yet. Register your first service to get started.</div>';
        }
    } catch (error) {
        display.innerHTML = '<div class="error"><i class="fas fa-exclamation-triangle"></i> Failed to load services</div>';
    }
}

async function searchDocumentation() {
    const query = document.getElementById('search-input').value.trim();
    if (!query) return;

    const resultsDisplay = document.getElementById('search-results');
    resultsDisplay.innerHTML = '<div class="loading"><i class="fas fa-spinner fa-spin"></i> Searching documentation...</div>';

    try {
        const response = await API.post('/docs/search', { query });
        if (response.results && response.results.length > 0) {
            resultsDisplay.innerHTML = response.results.map(result => `
                <div class="search-result">
                    <div class="result-source">${result.service_name} - ${result.doc_name}</div>
                    <div class="result-content">${result.content_preview}</div>
                </div>
            `).join('');
        } else {
            resultsDisplay.innerHTML = '<div class="no-results"><i class="fas fa-search"></i> No results found for your query.</div>';
        }
    } catch (error) {
        resultsDisplay.innerHTML = '<div class="error"><i class="fas fa-exclamation-triangle"></i> Search failed</div>';
    }
}

// Make functions globally available
window.loadServices = loadServices;
window.searchDocumentation = searchDocumentation;

console.log('Service Documentation functions attached to window');
