#!/usr/bin/env python3
import boto3
import json
import argparse
import sys

def get_stack_outputs(stack_name):
    """Get CloudFormation stack outputs"""
    try:
        cf = boto3.client('cloudformation')
        response = cf.describe_stacks(StackName=stack_name)
        outputs = response['Stacks'][0].get('Outputs', [])
        return {output['OutputKey']: output['OutputValue'] for output in outputs}
    except Exception as e:
        print(f"Error getting stack outputs: {e}")
        return {}

def detect_deployed_modules(stack_name, environment):
    """Detect which modules are deployed by checking stack outputs"""
    modules = {
        'security': False,
        'drift': False,
        'costs': False,
        'docs': False,
        'eol': False,
        'monitoring': False,
        'integrations': False,
        'incident-hub': False,
        'code-reviews': False
    }

    try:
        # Check main stack outputs
        outputs = get_stack_outputs(stack_name)
        if 'SecurityFindingsTableName' in outputs:
            modules['security'] = True
        if 'TerraformPlansTableName' in outputs:
            modules['drift'] = True
        if 'CostCacheTableName' in outputs:
            modules['costs'] = True
        if 'ServiceDocsTableName' in outputs:
            modules['docs'] = True
        if 'EOLDatabaseTableName' in outputs:
            modules['eol'] = True
        if 'ResourceDiscoveryTableName' in outputs:
            modules['monitoring'] = True
        if 'SlackUserMappingTable' in outputs:
            modules['integrations'] = True
        if 'PostmortemsTable' in outputs:
            modules['incident-hub'] = True
        if 'PRReviewsTableName' in outputs:
            modules['code-reviews'] = True
    except Exception as e:
        print(f"Warning: Could not detect modules from stack {stack_name}: {e}")

    return modules

def generate_config(stack_name, environment):
    """Generate frontend configuration with feature flags"""
    import os
    outputs = get_stack_outputs(stack_name)
    modules = detect_deployed_modules(stack_name, environment)

    api_url = outputs.get('CloudOpsAssistantApi', 'http://localhost:3001')
    user_pool_id = outputs.get('UserPoolId', 'us-east-1_example')
    user_pool_client_id = outputs.get('UserPoolClientId', 'example123')

    # Get GitHub configuration from frontend .env file
    github_target = ''
    github_token = ''
    try:
        with open('frontend/.env', 'r') as f:
            for line in f:
                if line.startswith('VITE_GITHUB_DEFAULT_TARGET='):
                    github_target = line.split('=', 1)[1].strip()
                elif line.startswith('VITE_GITHUB_DEFAULT_TOKEN='):
                    github_token = line.split('=', 1)[1].strip()
    except FileNotFoundError:
        pass

    config = f"""// Auto-generated configuration
const CONFIG = {{
    API_BASE_URL: '{api_url}',
    USER_POOL_ID: '{user_pool_id}',
    USER_POOL_CLIENT_ID: '{user_pool_client_id}',
    ENVIRONMENT: '{environment}',
    CURRENT_DAY: 18,

    // GitHub Configuration for auto-scanning
    GITHUB_DEFAULT_TARGET: '{github_target}',
    GITHUB_DEFAULT_TOKEN: '{github_token}',

    // Feature flags - automatically detected from deployed modules
    FEATURES: {{
        SECURITY: {str(modules['security']).lower()},
        DRIFT: {str(modules['drift']).lower()},
        COSTS: {str(modules['costs']).lower()},
        DOCS: {str(modules['docs']).lower()},
        EOL: {str(modules['eol']).lower()},
        MONITORING: {str(modules['monitoring']).lower()},
        INTEGRATIONS: {str(modules['integrations']).lower()},
        INCIDENT_HUB: {str(modules['incident-hub']).lower()},
        CODE_REVIEWS: {str(modules['code-reviews']).lower()}
    }}
}};

// Legacy support
window.CONFIG = CONFIG;
"""

    # Write to frontend config.js
    with open('frontend/config.js', 'w') as f:
        f.write(config)

    print(f"Generated frontend config with features: {[k for k, v in modules.items() if v]}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generate frontend configuration')
    parser.add_argument('--stack-name', required=True, help='CloudFormation stack name')
    parser.add_argument('--environment', default='dev', help='Environment name')

    args = parser.parse_args()
    generate_config(args.stack_name, args.environment)
