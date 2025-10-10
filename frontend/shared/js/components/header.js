// Header component
function initializeHeader(activeApp = '') {
    const headerContainer = document.getElementById('app-header');
    if (!headerContainer) return;

    headerContainer.innerHTML = `
        <header class="header">
            <div class="header-content">
                <div class="logo">
                    <i class="fas fa-cloud"></i>
                    <h1>CloudOps Assistant</h1>
                    ${activeApp ? `<span class="app-name">- ${activeApp}</span>` : ''}
                </div>
                <div class="header-right">
                    <div class="user-section" id="user-section">
                        <span id="user-email"></span>
                        <button class="btn btn-secondary" onclick="logout()">Logout</button>
                    </div>
                    <div class="nav-links">
                        <a href="../../index.html" class="nav-link">
                            <i class="fas fa-home"></i> Dashboard
                        </a>
                    </div>
                </div>
            </div>
        </header>
    `;

    checkAuthStatus();
    startTokenExpirationCheck();
}
