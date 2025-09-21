// Local Development Configuration
window.CONFIG = {
    // API Configuration
    API_BASE_URL: 'http://localhost:8080',
    AWS_REGION: 'us-east-1',

    // App Configuration
    APP_NAME: 'CloudOps Assistant (Local)',
    VERSION: '1.0.0-dev',
    ENVIRONMENT: 'local',
    CURRENT_DAY: 14,
    TOTAL_DAYS: 30,

    // Feature Flags
    FEATURES: {
        DRIFT_DETECTION: true,
        COST_DASHBOARD: true,
        AI_FEATURES: false  // Disabled in local mode
    },

    // Security
    MAX_FILE_SIZE: 10485760,
    ALLOWED_FILE_TYPES: ['.txt', '.log', '.out', '.plan'],

    // GitHub Configuration
    GITHUB_DEFAULT_TARGET: 'rmnicholson0612',
    GITHUB_DEFAULT_TOKEN: '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',

    // Local Development Features
    MOCK_AUTH: true,

    // Utility Functions
    sanitizeInput: function(input) {
        if (typeof input !== 'string') return input;
        return input.replace(/[<>"'&]/g, '').substring(0, 1000);
    }
};

console.log('CloudOps Assistant Config Loaded (Local):', window.CONFIG.ENVIRONMENT);
