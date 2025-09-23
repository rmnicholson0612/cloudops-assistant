#!/usr/bin/env node

/**
 * Build script to generate config.js from template and .env file
 * Preserves custom configurations while updating auto-generated values
 * Usage: node build-config.js [--local]
 */

const fs = require('fs');
const path = require('path');

// Check if --local flag is provided
const isLocal = process.argv.includes('--local');
const envFile = isLocal ? '.env.local' : '.env';
const templateFile = 'config.template.js';
const outputFile = 'config.js';

console.log(`Building ${outputFile} from ${templateFile} and ${envFile}...`);

// Read environment file
let envContent = '';
try {
    envContent = fs.readFileSync(path.join(__dirname, envFile), 'utf8');
} catch (error) {
    console.warn(`Warning: Could not read ${envFile}, using defaults`);
}

// Parse environment variables
const envVars = {};
envContent.split('\n').forEach(line => {
    line = line.trim();
    if (line && !line.startsWith('#')) {
        const [key, ...valueParts] = line.split('=');
        if (key && key.startsWith('VITE_')) {
            envVars[key] = valueParts.join('=').replace(/^["']|["']$/g, ''); // Remove quotes
        }
    }
});

// Read template file
let templateContent = '';
try {
    templateContent = fs.readFileSync(path.join(__dirname, templateFile), 'utf8');
} catch (error) {
    console.error(`Error reading ${templateFile}:`, error.message);
    process.exit(1);
}

// Extract custom configuration from existing config.js if it exists
let customConfig = '';
try {
    const existingConfig = fs.readFileSync(path.join(__dirname, outputFile), 'utf8');
    const startMarker = '// {{CUSTOM_CONFIG_START}}';
    const endMarker = '// {{CUSTOM_CONFIG_END}}';
    const startIndex = existingConfig.indexOf(startMarker);
    const endIndex = existingConfig.indexOf(endMarker);

    if (startIndex !== -1 && endIndex !== -1) {
        customConfig = existingConfig.substring(startIndex + startMarker.length, endIndex).trim();
        console.log('✅ Preserved custom configuration');
    }
} catch (error) {
    console.log('ℹ️  No existing config.js found, using template defaults');
}

// Replace template variables
let configContent = templateContent
    .replace('{{API_BASE_URL}}', envVars.VITE_API_BASE_URL || 'http://localhost:8080')
    .replace('{{AWS_REGION}}', envVars.VITE_AWS_REGION || 'us-east-1')
    .replace('{{APP_NAME}}', envVars.VITE_APP_NAME || 'CloudOps Assistant')
    .replace('{{VERSION}}', envVars.VITE_VERSION || '1.0.0')
    .replace('{{ENVIRONMENT}}', envVars.VITE_ENVIRONMENT || 'development')
    .replace('{{CURRENT_DAY}}', envVars.VITE_CURRENT_DAY || '15')
    .replace('{{TOTAL_DAYS}}', envVars.VITE_TOTAL_DAYS || '30')
    .replace('{{DRIFT_DETECTION}}', (envVars.VITE_ENABLE_DRIFT_DETECTION === 'true').toString())
    .replace('{{COST_DASHBOARD}}', (envVars.VITE_ENABLE_COST_DASHBOARD === 'true').toString())
    .replace('{{AI_FEATURES}}', (envVars.VITE_ENABLE_AI_FEATURES === 'true').toString())
    .replace('{{MAX_FILE_SIZE}}', envVars.VITE_MAX_FILE_SIZE || '10485760')
    .replace('{{GITHUB_DEFAULT_TARGET}}', envVars.VITE_GITHUB_DEFAULT_TARGET || '')
    .replace('{{GITHUB_DEFAULT_TOKEN}}', envVars.VITE_GITHUB_DEFAULT_TOKEN || '');

// Insert custom configuration
if (customConfig) {
    const customMarkerStart = '// {{CUSTOM_CONFIG_START}}';
    const customMarkerEnd = '// {{CUSTOM_CONFIG_END}}';
    const startIndex = configContent.indexOf(customMarkerStart);
    const endIndex = configContent.indexOf(customMarkerEnd);

    if (startIndex !== -1 && endIndex !== -1) {
        configContent = configContent.substring(0, startIndex + customMarkerStart.length) +
                      '\n\n' + customConfig + '\n\n    ' +
                      configContent.substring(endIndex);
    }
}

// Write config.js
try {
    fs.writeFileSync(path.join(__dirname, outputFile), configContent);
    console.log(`✅ ${outputFile} generated successfully`);
    console.log(`   Environment: ${envVars.VITE_ENVIRONMENT || 'development'}`);
    console.log(`   API URL: ${envVars.VITE_API_BASE_URL || 'http://localhost:8080'}`);
    if (customConfig) {
        console.log(`   Custom config: Preserved`);
    }
} catch (error) {
    console.error(`Error writing ${outputFile}:`, error.message);
    process.exit(1);
}
