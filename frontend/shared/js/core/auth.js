// Authentication utilities
function checkAuthStatus() {
    if (API.isAuthenticated()) {
        updateAuthUI();
    }
}

function startTokenExpirationCheck() {
    setInterval(() => {
        if (!API.isAuthenticated()) {
            updateAuthUI();
        }
    }, 5 * 60 * 1000); // 5 minutes
}

function updateAuthUI() {
    const email = localStorage.getItem('user_email');
    const userSection = document.getElementById('user-section');

    if (API.isAuthenticated() && email) {
        if (userSection) {
            userSection.style.display = 'block';
            const userEmail = document.getElementById('user-email');
            if (userEmail) userEmail.textContent = email;
        }
    } else {
        if (userSection) userSection.style.display = 'none';
    }
}

function logout() {
    if (typeof API !== 'undefined' && API.logout) {
        API.logout();
    } else {
        localStorage.removeItem('access_token');
        localStorage.removeItem('user_email');
        window.location.href = '../../login.html';
    }
}
