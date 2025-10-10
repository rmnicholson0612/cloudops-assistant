// Example configuration with feature flags
const CONFIG = {
    API_BASE_URL: 'https://your-api-gateway-url.execute-api.us-east-1.amazonaws.com/Prod/',
    USER_POOL_ID: 'us-east-1_YourPoolId',
    USER_POOL_CLIENT_ID: 'your-client-id',
    ENVIRONMENT: 'dev',
    CURRENT_DAY: 18,

    // Feature flags - set to true/false based on deployed modules
    FEATURES: {
        SECURITY: true,        // Security Hub module
        DRIFT: true,          // Drift Detection module
        COSTS: true,          // Cost Dashboard module
        DOCS: false,          // Service Documentation module
        EOL: false,           // EOL Tracker module
        MONITORING: false,    // Resource Discovery module
        INTEGRATIONS: false,  // Slack/GitHub integrations
        INCIDENT_HUB: false,  // Postmortem generator
        CODE_REVIEWS: false   // PR review automation
    }
};

// Legacy support
window.CONFIG = CONFIG;
