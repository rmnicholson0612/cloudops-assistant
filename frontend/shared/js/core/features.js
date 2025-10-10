// Feature detection and management
class FeatureManager {
    constructor() {
        this.features = {};
        this.initialized = false;
    }

    async initialize() {
        if (this.initialized) return;

        // Use config-based feature flags if available, otherwise detect
        if (window.CONFIG && window.CONFIG.FEATURES) {
            this.features = {
                'security': window.CONFIG.FEATURES.SECURITY,
                'drift': window.CONFIG.FEATURES.DRIFT,
                'costs': window.CONFIG.FEATURES.COSTS,
                'docs': window.CONFIG.FEATURES.DOCS,
                'eol': window.CONFIG.FEATURES.EOL,
                'monitoring': window.CONFIG.FEATURES.MONITORING,
                'integrations': window.CONFIG.FEATURES.INTEGRATIONS,
                'incident-hub': window.CONFIG.FEATURES.INCIDENT_HUB,
                'code-reviews': window.CONFIG.FEATURES.CODE_REVIEWS
            };
        } else {
            await this.detectFeatures();
        }

        this.initialized = true;
    }

    async detectFeatures() {
        const token = localStorage.getItem('access_token');
        if (!token) return;

        // Test each feature endpoint to see if it's available
        const featureTests = [
            { name: 'security', endpoint: '/security/accounts', method: 'GET' },
            { name: 'drift', endpoint: '/drift/status', method: 'GET' },
            { name: 'costs', endpoint: '/costs/current', method: 'GET' },
            { name: 'docs', endpoint: '/docs/services', method: 'GET' },
            { name: 'eol', endpoint: '/eol/database', method: 'GET' },
            { name: 'monitoring', endpoint: '/discovery/scans', method: 'GET' },
            { name: 'integrations', endpoint: '/slack/link', method: 'GET' },
            { name: 'incident-hub', endpoint: '/postmortems', method: 'GET' },
            { name: 'code-reviews', endpoint: '/pr-reviews', method: 'GET' }
        ];

        for (const test of featureTests) {
            try {
                const response = await fetch(`${CONFIG.API_BASE_URL}${test.endpoint}`, {
                    method: test.method,
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                this.features[test.name] = response.status !== 404;
            } catch (error) {
                this.features[test.name] = false;
            }
        }
    }

    isEnabled(featureName) {
        return this.features[featureName] === true;
    }

    getEnabledFeatures() {
        return Object.keys(this.features).filter(name => this.features[name]);
    }

    hideDisabledFeatures() {
        // Hide app cards for disabled features
        const appCards = document.querySelectorAll('.app-card[data-feature]');
        appCards.forEach(card => {
            const feature = card.getAttribute('data-feature');
            if (!this.isEnabled(feature)) {
                card.style.display = 'none';
            }
        });

        console.log('Enabled features:', this.getEnabledFeatures());
    }
}

// Global feature manager instance
window.featureManager = new FeatureManager();
