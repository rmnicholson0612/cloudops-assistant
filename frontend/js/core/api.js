// Core API utilities for CloudOps Assistant
// Handles authentication, common API patterns, and error handling

const API = {
    // Check if user is authenticated
    isAuthenticated() {
        return !!localStorage.getItem('access_token');
    },

    // Get auth headers for API calls
    getAuthHeaders() {
        const token = localStorage.getItem('access_token');
        return {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
        };
    },

    // Show authentication required message
    requireAuth() {
        if (!this.isAuthenticated()) {
            alert('Please login first');
            return false;
        }
        return true;
    },

    // Make authenticated GET request
    async get(endpoint) {
        if (!this.requireAuth()) return null;

        try {
            const response = await fetch(`${window.CONFIG.API_BASE_URL}${endpoint}`, {
                headers: { 'Authorization': `Bearer ${localStorage.getItem('access_token')}` }
            });

            if (response.ok) {
                return await response.json();
            } else {
                throw new Error(`API Error: ${response.status}`);
            }
        } catch (error) {
            console.error(`GET ${endpoint} failed:`, error);
            throw error;
        }
    },

    // Make authenticated POST request
    async post(endpoint, data) {
        if (!this.requireAuth()) return null;

        try {
            const response = await fetch(`${window.CONFIG.API_BASE_URL}${endpoint}`, {
                method: 'POST',
                headers: this.getAuthHeaders(),
                body: JSON.stringify(data)
            });

            if (response.ok) {
                return await response.json();
            } else {
                const error = await response.json();
                throw new Error(error.error || `API Error: ${response.status}`);
            }
        } catch (error) {
            console.error(`POST ${endpoint} failed:`, error);
            throw error;
        }
    },

    // Make authenticated PUT request
    async put(endpoint, data) {
        if (!this.requireAuth()) return null;

        try {
            const response = await fetch(`${window.CONFIG.API_BASE_URL}${endpoint}`, {
                method: 'PUT',
                headers: this.getAuthHeaders(),
                body: JSON.stringify(data)
            });

            if (response.ok) {
                return await response.json();
            } else {
                const error = await response.json();
                throw new Error(error.error || `API Error: ${response.status}`);
            }
        } catch (error) {
            console.error(`PUT ${endpoint} failed:`, error);
            throw error;
        }
    },

    // Make authenticated DELETE request
    async delete(endpoint) {
        if (!this.requireAuth()) return null;

        try {
            const response = await fetch(`${window.CONFIG.API_BASE_URL}${endpoint}`, {
                method: 'DELETE',
                headers: this.getAuthHeaders()
            });

            if (response.ok) {
                return await response.json();
            } else {
                const error = await response.json();
                throw new Error(error.error || `API Error: ${response.status}`);
            }
        } catch (error) {
            console.error(`DELETE ${endpoint} failed:`, error);
            throw error;
        }
    },

    // Show loading state in element
    showLoading(elementId, message = 'Loading...') {
        const element = document.getElementById(elementId);
        if (element) {
            element.innerHTML = `<i class="fas fa-spinner fa-spin"></i> ${message}`;
        }
    },

    // Show error in element
    showError(elementId, message) {
        const element = document.getElementById(elementId);
        if (element) {
            element.innerHTML = `<p>Error: ${message}</p>`;
        }
    },

    // Show success message in element
    showSuccess(elementId, message) {
        const element = document.getElementById(elementId);
        if (element) {
            element.innerHTML = `<p>${message}</p>`;
        }
    }
};
