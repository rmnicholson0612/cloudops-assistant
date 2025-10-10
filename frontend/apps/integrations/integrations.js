// Integrations App Module
console.log('Integrations script loaded');

function initializeIntegrations() {
    console.log('Integrations initialized');
}

async function loadSlackStatus() {
    const display = document.getElementById('slack-status-display');
    display.innerHTML = '<div class="slack-loading"><i class="fas fa-spinner fa-spin"></i> Loading Slack bot status...</div>';

    // Since there's no /slack/status endpoint, show configuration info
    display.innerHTML = `
        <div class="slack-not-configured">
            <i class="fas fa-info-circle"></i>
            <span>Slack bot integration available. Click "Configure Slack Bot" to set up.</span>
            <div class="slack-commands">
                <p>Available commands once configured:</p>
                <ul>
                    <li><code>/cloudops status</code> - Infrastructure overview</li>
                    <li><code>/cloudops drift</code> - Check for drift</li>
                    <li><code>/cloudops costs</code> - Cost analysis</li>
                    <li><code>/cloudops register</code> - Link your account</li>
                </ul>
            </div>
        </div>
    `;
}

function showSlackSetupModal() {
    const modal = document.getElementById('slack-setup-modal');
    const eventsUrl = document.getElementById('slack-events-url');
    const commandsUrl = document.getElementById('slack-commands-url');

    eventsUrl.value = `${window.CONFIG.API_BASE_URL}slack/events`;
    commandsUrl.value = `${window.CONFIG.API_BASE_URL}slack/commands`;

    modal.style.display = 'block';
}

function closeSlackSetupModal() {
    document.getElementById('slack-setup-modal').style.display = 'none';
}

function copyToClipboard(elementId) {
    const element = document.getElementById(elementId);
    element.select();
    document.execCommand('copy');

    const button = element.nextElementSibling;
    const originalText = button.innerHTML;
    button.innerHTML = '<i class="fas fa-check"></i>';
    setTimeout(() => {
        button.innerHTML = originalText;
    }, 1000);
}

window.onclick = function(event) {
    const modal = document.getElementById('slack-setup-modal');
    if (event.target === modal) {
        closeSlackSetupModal();
    }
}

// Make functions globally available
window.loadSlackStatus = loadSlackStatus;
window.showSlackSetupModal = showSlackSetupModal;
window.closeSlackSetupModal = closeSlackSetupModal;
window.copyToClipboard = copyToClipboard;

console.log('Integrations functions attached to window');
