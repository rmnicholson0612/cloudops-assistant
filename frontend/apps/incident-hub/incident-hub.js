// Incident Hub App Module
console.log('Incident Hub script loaded');

function initializeIncidentHub() {
    console.log('Incident Hub initialized');
}

async function loadPostmortems() {
    const display = document.getElementById('postmortems-display');
    if (!display) return;

    display.innerHTML = '<div class="loading"><i class="fas fa-spinner fa-spin"></i> Loading postmortems...</div>';

    try {
        const response = await API.get('/postmortems');
        if (response.postmortems && response.postmortems.length > 0) {
            display.innerHTML = response.postmortems.map(pm => `
                <div class="postmortem-item">
                    <h4>${pm.title || 'Incident Postmortem'}</h4>
                    <div class="postmortem-summary">${pm.summary || 'No summary available'}</div>
                    <div class="postmortem-meta">
                        <span class="severity severity-${(pm.severity || 'unknown').toLowerCase()}">${pm.severity || 'Unknown'}</span>
                        <span class="timestamp">${new Date(pm.created_at).toLocaleString()}</span>
                    </div>
                </div>
            `).join('');
        } else {
            display.innerHTML = '<div class="no-data"><i class="fas fa-info-circle"></i> No postmortems available. Create your first postmortem to get started.</div>';
        }
    } catch (error) {
        display.innerHTML = '<div class="error"><i class="fas fa-exclamation-triangle"></i> Failed to load postmortems</div>';
    }
}

function showCreatePostmortemModal() {
    window.open('conversational-postmortem.html', '_blank');
}

// Make functions globally available
window.loadPostmortems = loadPostmortems;
window.showCreatePostmortemModal = showCreatePostmortemModal;

console.log('Incident Hub functions attached to window');
