#!/usr/bin/env node

/**
 * Build script to generate config.js from .env file
 * Usage: node build-config.js [--local]
 */

const fs = require('fs');
const path = require('path');

// Check if --local flag is provided
const isLocal = process.argv.includes('--local');
const envFile = isLocal ? '.env.local' : '.env';
const configTemplate = isLocal ? 'config.local.js' : 'config.js.example';
const outputFile = 'config.js';

console.log(`Building ${outputFile} from ${envFile}...`);

// Read environment file
let envContent = '';
try {
    envContent = fs.readFileSync(path.join(__dirname, envFile), 'utf8');
} catch (error) {
    console.error(`Error reading ${envFile}:`, error.message);
    process.exit(1);
}

// Parse environment variables
const envVars = {};
envContent.split('\n').forEach(line => {
    line = line.trim();
    if (line && !line.startsWith('#')) {
        const [key, ...valueParts] = line.split('=');
        if (key && key.startsWith('VITE_')) {
            envVars[key] = valueParts.join('=');
        }
    }
});

// Generate config.js content
const configContent = `// CloudOps Assistant Frontend Configuration
// Generated automatically - DO NOT EDIT MANUALLY
// Update frontend/${envFile} to change these values

window.CONFIG = {
    // API Configuration
    API_BASE_URL: '${envVars.VITE_API_BASE_URL || 'http://localhost:8080'}',
    AWS_REGION: '${envVars.VITE_AWS_REGION || 'us-east-1'}',

    // App Configuration
    APP_NAME: '${envVars.VITE_APP_NAME || 'CloudOps Assistant'}',
    VERSION: '${envVars.VITE_VERSION || '1.0.0'}',
    ENVIRONMENT: '${envVars.VITE_ENVIRONMENT || 'development'}',
    CURRENT_DAY: ${envVars.VITE_CURRENT_DAY || 14},
    TOTAL_DAYS: ${envVars.VITE_TOTAL_DAYS || 30},

    // Feature Flags
    FEATURES: {
        DRIFT_DETECTION: ${envVars.VITE_ENABLE_DRIFT_DETECTION === 'true'},
        COST_DASHBOARD: ${envVars.VITE_ENABLE_COST_DASHBOARD === 'true'},
        AI_FEATURES: ${envVars.VITE_ENABLE_AI_FEATURES === 'true'}
    },

    // Security
    MAX_FILE_SIZE: ${envVars.VITE_MAX_FILE_SIZE || 10485760},
    ALLOWED_FILE_TYPES: ['.txt', '.log', '.out', '.plan'],

    // GitHub Configuration
    GITHUB_DEFAULT_TARGET: '${envVars.VITE_GITHUB_DEFAULT_TARGET || ''}',
    GITHUB_DEFAULT_TOKEN: '${envVars.VITE_GITHUB_DEFAULT_TOKEN || ''}',

    // Utility Functions
    sanitizeInput: function(input) {
        if (typeof input !== 'string') return input;
        return input.replace(/[<>"'&]/g, '').substring(0, 1000);
    }
};

console.log('CloudOps Assistant Config Loaded:', window.CONFIG.ENVIRONMENT);
`;

// Write config.js
try {
    fs.writeFileSync(path.join(__dirname, outputFile), configContent);
    console.log(`✅ ${outputFile} generated successfully`);
    console.log(`   Environment: ${envVars.VITE_ENVIRONMENT || 'development'}`);
    console.log(`   API URL: ${envVars.VITE_API_BASE_URL || 'http://localhost:8080'}`);
} catch (error) {
    console.error(`Error writing ${outputFile}:`, error.message);
    process.exit(1);
}
