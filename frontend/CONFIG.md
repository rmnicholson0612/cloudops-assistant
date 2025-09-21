# Frontend Configuration Guide

## Overview

The CloudOps Assistant frontend uses a consolidated configuration system with the following files:

- **`.env`** - Production environment variables
- **`.env.example`** - Template for environment variables
- **`config.js`** - Generated production configuration (DO NOT EDIT)
- **`config.local.js`** - Local development configuration
- **`config.js.example`** - Template for generated configuration
- **`build-config.js`** - Build script to generate config.js from .env

## Configuration Structure

All configurations follow this standardized structure:

```javascript
window.CONFIG = {
    // API Configuration
    API_BASE_URL: 'https://api-url.com',
    AWS_REGION: 'us-east-1',

    // App Configuration
    APP_NAME: 'CloudOps Assistant',
    VERSION: '1.0.0',
    ENVIRONMENT: 'production',
    CURRENT_DAY: 14,
    TOTAL_DAYS: 30,

    // Feature Flags
    FEATURES: {
        DRIFT_DETECTION: true,
        COST_DASHBOARD: true,
        AI_FEATURES: true
    },

    // Security
    MAX_FILE_SIZE: 10485760,
    ALLOWED_FILE_TYPES: ['.txt', '.log', '.out', '.plan'],

    // GitHub Configuration
    GITHUB_DEFAULT_TARGET: 'your-github-username',
    GITHUB_DEFAULT_TOKEN: '',

    // Utility Functions
    sanitizeInput: function(input) { /* ... */ }
};
```

## Environment Variables

All environment variables use the `VITE_` prefix:

| Variable | Description | Default |
|----------|-------------|---------|
| `VITE_API_BASE_URL` | Backend API URL | `http://localhost:8080` |
| `VITE_AWS_REGION` | AWS region | `us-east-1` |
| `VITE_APP_NAME` | Application name | `CloudOps Assistant` |
| `VITE_VERSION` | Application version | `1.0.0` |
| `VITE_ENVIRONMENT` | Environment (production/development/local) | `development` |
| `VITE_CURRENT_DAY` | Current project day | `14` |
| `VITE_TOTAL_DAYS` | Total project days | `30` |
| `VITE_ENABLE_DRIFT_DETECTION` | Enable drift detection | `true` |
| `VITE_ENABLE_COST_DASHBOARD` | Enable cost dashboard | `true` |
| `VITE_ENABLE_AI_FEATURES` | Enable AI features | `true` |
| `VITE_GITHUB_DEFAULT_TARGET` | Default GitHub username/org | `your-github-username` |
| `VITE_GITHUB_DEFAULT_TOKEN` | Default GitHub token | `` |
| `VITE_MAX_FILE_SIZE` | Maximum file upload size | `10485760` |

## Usage

### Production Deployment

1. Update `.env` with your production values
2. Run the build script: `node build-config.js`
3. Deploy the generated `config.js` with your frontend

### Local Development

1. Use `config.local.js` directly (no build step needed)
2. Modify values directly in the file
3. Set `AI_FEATURES: false` for local development without AWS

### Build Script

Generate `config.js` from environment variables:

```bash
# Generate production config
node build-config.js

# Generate local config (if .env.local exists)
node build-config.js --local
```

## File Hierarchy

1. **Local Development**: `config.local.js` (manual configuration)
2. **Production**: `config.js` (generated from `.env`)
3. **Templates**: `config.js.example` and `.env.example` (for reference)

## Migration from Old System

The old system had:
- Duplicate configurations across files
- Hardcoded values in HTML
- Inconsistent naming conventions

The new system:
- ✅ Single source of truth (`.env` files)
- ✅ Consistent structure across all environments
- ✅ Automated generation from environment variables
- ✅ No hardcoded values in HTML
- ✅ Clear separation between local and production configs

## Best Practices

1. **Never edit `config.js` directly** - it's generated automatically
2. **Use `.env` for production settings**
3. **Use `config.local.js` for local development**
4. **Keep sensitive tokens out of version control**
5. **Update both `.env` and `.env.example` when adding new variables**
6. **Run build script after changing `.env`**

## Troubleshooting

### Config not loading
- Check that `config.js` exists and is valid JavaScript
- Verify the script tag in `index.html` loads before other scripts

### Values not updating
- Regenerate `config.js` with `node build-config.js`
- Clear browser cache
- Check console for JavaScript errors

### Local development issues
- Ensure `config.local.js` exists
- Verify `MOCK_AUTH: true` for local development
- Check that `AI_FEATURES: false` if AWS services unavailable locally
