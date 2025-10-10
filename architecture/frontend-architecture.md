# Frontend Architecture

## Modular App Structure

The frontend has been restructured into a modular architecture where each major feature is a standalone app.

### Directory Structure

```
frontend/
├── apps/                          # Individual applications
│   ├── drift-detection/           # Drift Detection App (Complete)
│   │   ├── index.html            # Standalone app page
│   │   ├── drift-detection.js    # App-specific functionality
│   │   └── drift-detection.css   # App-specific styles
│   ├── cost-dashboard/           # Cost Dashboard App (Coming Soon)
│   └── security/                 # Security Hub App (Coming Soon)
├── shared/                       # Shared components and utilities
│   ├── js/
│   │   ├── core/
│   │   │   ├── api.js            # API client
│   │   │   └── auth.js           # Authentication utilities
│   │   └── components/
│   │       └── header.js         # Reusable header component
│   ├── css/
│   │   ├── base.css              # Base styles (layout, typography)
│   │   └── components.css        # Reusable component styles
│   └── assets/
│       └── favicon.svg           # Shared assets
├── index.html                    # Main dashboard (app launcher)
├── login.html                    # Authentication page
└── config.js                     # Global configuration
```

## Benefits of This Architecture

### 1. **Separation of Concerns**
- Each app is self-contained with its own HTML, CSS, and JavaScript
- Shared functionality is centralized in the `shared/` directory
- Main dashboard serves as an app launcher

### 2. **Independent Development**
- Apps can be developed, tested, and deployed independently
- Changes to one app don't affect others
- Easier to maintain and debug

### 3. **Scalability**
- Easy to add new apps without modifying existing ones
- Shared components can be reused across apps
- Clear boundaries between features

### 4. **Performance**
- Only load the code needed for each app
- Smaller bundle sizes per app
- Better caching strategies

## How to Add a New App

1. **Create App Directory**
   ```bash
   mkdir frontend/apps/my-new-app
   ```

2. **Create App Files**
   ```bash
   # App HTML
   touch frontend/apps/my-new-app/index.html

   # App JavaScript
   touch frontend/apps/my-new-app/my-new-app.js

   # App Styles
   touch frontend/apps/my-new-app/my-new-app.css
   ```

3. **Use App Template**
   ```html
   <!DOCTYPE html>
   <html lang="en">
   <head>
       <meta charset="UTF-8">
       <meta name="viewport" content="width=device-width, initial-scale=1.0">
       <title>CloudOps Assistant - My New App</title>
       <link rel="icon" type="image/svg+xml" href="../../shared/assets/favicon.svg">
       <link rel="stylesheet" href="../../shared/css/base.css">
       <link rel="stylesheet" href="../../shared/css/components.css">
       <link rel="stylesheet" href="my-new-app.css">
       <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
       <script src="../../config.js"></script>
       <script src="../../shared/js/core/api.js"></script>
       <script src="../../shared/js/core/auth.js"></script>
       <script src="../../shared/js/components/header.js"></script>
       <script src="my-new-app.js"></script>
   </head>
   <body>
       <div class="app">
           <!-- Header Component -->
           <div id="app-header"></div>

           <!-- Main Content -->
           <main class="main-content">
               <div class="feature-header">
                   <h2><i class="fas fa-icon"></i> My New App</h2>
                   <p>Description of what this app does</p>
               </div>

               <!-- App content goes here -->
           </main>
       </div>

       <script>
           document.addEventListener('DOMContentLoaded', function() {
               if (!API.isAuthenticated()) {
                   window.location.href = '../../login.html';
                   return;
               }

               initializeHeader('My New App');
               initializeMyNewApp();
           });

           function initializeMyNewApp() {
               // App initialization code
           }
       </script>
   </body>
   </html>
   ```

4. **Add to Main Dashboard**
   Update `frontend/index.html` to include a card for your new app.

## Shared Components

### Header Component
- Provides consistent navigation and branding
- Includes progress counter and user authentication status
- Automatically handles logout functionality

### API Client
- Centralized API communication
- Handles authentication tokens
- Provides common HTTP methods with error handling

### Authentication
- JWT token management
- Automatic token expiration checking
- Consistent login/logout flow

## Deployment Strategy

### Individual App Deployment
Each app can be deployed independently:
- Upload only the changed app files
- Shared components are cached by browsers
- Minimal deployment footprint

### Full Platform Deployment
For major updates affecting shared components:
- Deploy all apps and shared components
- Update version numbers for cache busting
- Test all apps after deployment

## Current Apps

### ✅ Drift Detection (Complete)
- **Path**: `apps/drift-detection/`
- **Features**: GitHub repository scanning, drift monitoring, terraform plan analysis
- **Status**: Production ready

### ✅ Cost Dashboard (Available)
- **Path**: `apps/cost-dashboard/`
- **Features**: AWS cost tracking, budget management, cost optimization
- **Status**: Functional

### ✅ Security Hub (Available)
- **Path**: `apps/security/`
- **Features**: Security scanning, compliance monitoring, vulnerability management
- **Status**: Functional

### ✅ Code Reviews (Available)
- **Path**: `apps/code-reviews/`
- **Features**: AI-powered PR reviews, security analysis
- **Status**: Functional

### ✅ Resource Monitoring (Available)
- **Path**: `apps/monitoring/`
- **Features**: AWS resource discovery, monitoring, optimization recommendations
- **Status**: Functional

### ✅ EOL Tracker (Available)
- **Path**: `apps/eol-tracker/`
- **Features**: End-of-life technology tracking, vulnerability scanning
- **Status**: Functional

### ✅ AI Assistant (Available)
- **Path**: `apps/ai-assistant/`
- **Features**: AI-powered infrastructure analysis and recommendations
- **Status**: Functional

## Migration Notes

The original monolithic dashboard has been converted to this modular structure:
- All drift detection functionality moved to standalone app
- Shared utilities extracted to common modules
- Main dashboard now serves as app launcher
- Authentication flow preserved across all apps
