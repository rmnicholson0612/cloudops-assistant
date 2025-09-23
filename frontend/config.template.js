// CloudOps Assistant Frontend Configuration Template
// This template is used to generate config.js
// Add your custom configurations here - they will be preserved during updates

window.CONFIG = {
    // API Configuration - AUTO-GENERATED (do not modify)
    API_BASE_URL: '{{API_BASE_URL}}',
    AWS_REGION: '{{AWS_REGION}}',

    // App Configuration - AUTO-GENERATED (do not modify)
    APP_NAME: '{{APP_NAME}}',
    VERSION: '{{VERSION}}',
    ENVIRONMENT: '{{ENVIRONMENT}}',
    CURRENT_DAY: {{CURRENT_DAY}},
    TOTAL_DAYS: {{TOTAL_DAYS}},

    // Feature Flags - AUTO-GENERATED (do not modify)
    FEATURES: {
        DRIFT_DETECTION: {{DRIFT_DETECTION}},
        COST_DASHBOARD: {{COST_DASHBOARD}},
        AI_FEATURES: {{AI_FEATURES}}
    },

    // Security - AUTO-GENERATED (do not modify)
    MAX_FILE_SIZE: {{MAX_FILE_SIZE}},
    ALLOWED_FILE_TYPES: ['.txt', '.log', '.out', '.plan'],

    // GitHub Configuration - AUTO-GENERATED (do not modify)
    GITHUB_DEFAULT_TARGET: '{{GITHUB_DEFAULT_TARGET}}',
    GITHUB_DEFAULT_TOKEN: '{{GITHUB_DEFAULT_TOKEN}}',

    // CUSTOM CONFIGURATION SECTION - Add your custom configs below
    // These will be preserved during auto-generation
    // {{CUSTOM_CONFIG_START}}

    // Add your custom configuration here
    // Example:
    // CUSTOM_FEATURE: true,
    // CUSTOM_ENDPOINT: 'https://example.com/api',

    // {{CUSTOM_CONFIG_END}}

    // Utility Functions - AUTO-GENERATED (do not modify)
    sanitizeInput: function(input) {
        if (typeof input !== 'string') return input;
        return input.replace(/[<>"'&]/g, '').substring(0, 1000);
    }
};

console.log('CloudOps Assistant Config Loaded:', window.CONFIG.ENVIRONMENT);
