// Monitoring App Module

function initializeMonitoring() {
    // Initialize any default state
}

async function discoverResources() {
    if (!API.requireAuth()) return;

    const display = document.getElementById('resource-discovery');
    display.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Discovering AWS resources...';

    try {
        const result = await API.post('/resources/discover');
        displayDiscoveredResources(result.resources || []);
    } catch (error) {
        display.innerHTML = `<p>Discovery failed: ${error.message}</p>`;
    }
}

function displayDiscoveredResources(resources) {
    const display = document.getElementById('resource-discovery');

    if (!resources || resources.length === 0) {
        display.innerHTML = '<p>No resources discovered.</p>';
        return;
    }

    display.innerHTML = `
        <div class="resources-grid">
            ${resources.map(resource => `
                <div class="resource-card">
                    <h5>${resource.type}</h5>
                    <p>${resource.name}</p>
                    <p>Region: ${resource.region}</p>
                </div>
            `).join('')}
        </div>
    `;
}
