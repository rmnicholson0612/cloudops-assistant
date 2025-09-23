"""
Test configuration for integration tests
Manages test environment settings and API endpoints
"""
import os
from typing import Dict, List, Tuple


class TestConfig:
    """Configuration for integration tests"""

    def __init__(self):
        self.api_base_url = self._get_api_base_url()
        self.test_timeout = 30
        self.retry_attempts = 3
        self.retry_delay = 1

    def _get_api_base_url(self) -> str:
        """Get API base URL from environment or use default"""
        # Try environment variable first
        api_url = os.environ.get("CLOUDOPS_TEST_API_URL")
        if api_url:
            return api_url.rstrip("/")

        # Try to read from deployed stack output
        try:
            import boto3
            cf_client = boto3.client("cloudformation")
            response = cf_client.describe_stacks(StackName="cloudops-assistant")

            for output in response["Stacks"][0]["Outputs"]:
                if output["OutputKey"] == "CloudOpsAssistantApi":
                    return output["OutputValue"].rstrip("/")
        except Exception:
            pass

        # Default to localhost for local development
        return "http://localhost:3000"

    @property
    def unauthenticated_endpoints(self) -> List[Tuple[str, str]]:
        """Endpoints that should be accessible without authentication"""
        return [
            ("/auth/register", "POST"),
            ("/auth/login", "POST"),
            ("/auth/verify", "POST"),
        ]

    @property
    def authenticated_endpoints(self) -> List[Tuple[str, str]]:
        """Endpoints that require authentication"""
        return [
            # Plan Management
            ("/upload-plan", "POST"),
            ("/plan-history/test-repo", "GET"),
            ("/plan-details/test-plan-id", "GET"),
            ("/compare-plans/plan1/plan2", "GET"),

            # Cost Analysis
            ("/costs/current", "GET"),
            ("/costs/services", "GET"),
            ("/costs/trends", "GET"),
            ("/costs/by-tag", "GET"),

            # Budget Management
            ("/budgets/status", "GET"),
            ("/budgets/configure", "POST"),
            ("/budgets/alerts", "GET"),
            ("/budgets/update/test-budget-id", "PUT"),
            ("/budgets/delete/test-budget-id", "DELETE"),

            # Drift Monitoring
            ("/drift/status", "GET"),
            ("/drift/configure", "POST"),
            ("/drift/update/test-config-id", "PUT"),
            ("/drift/delete/test-config-id", "DELETE"),
            ("/drift/scan/test-config-id", "POST"),

            # Repository Scanning
            ("/scan-repos", "POST"),

            # AI Features
            ("/ai/explain", "POST"),
            ("/ai/explanations", "GET"),

            # Postmortems
            ("/postmortems", "GET"),
            ("/postmortems", "POST"),
            ("/postmortems/test-postmortem-id", "GET"),
            ("/postmortems/test-postmortem-id", "PUT"),
            ("/postmortems/test-postmortem-id", "DELETE"),
            ("/postmortems/generate", "POST"),
            ("/postmortems/suggest", "POST"),
            ("/postmortems/previous", "POST"),
            ("/postmortems/conversation", "POST"),
            ("/users", "GET"),

            # Resource Discovery
            ("/discovery/scan", "POST"),
            ("/discovery/results", "GET"),
            ("/discovery/history", "GET"),

            # Service Documentation
            ("/docs/services", "GET"),
            ("/docs/register", "POST"),
            ("/docs/upload", "POST"),
            ("/docs/search", "POST"),
            ("/docs/list", "GET"),
            ("/docs/get", "POST"),
            ("/docs/delete", "DELETE"),

            # EOL Tracker
            ("/eol/scan", "POST"),
            ("/eol/results", "GET"),
            ("/eol/database", "GET"),
            ("/eol/update", "POST"),

            # PR Reviews
            ("/pr-reviews", "GET"),
            ("/pr-reviews/test-review-id", "GET"),
            ("/pr-reviews/configure", "POST"),
        ]

    def get_test_user_credentials(self, suffix: str = "") -> Dict[str, str]:
        """Generate test user credentials"""
        import time
        timestamp = int(time.time())
        return {
            "email": f"test-user-{timestamp}{suffix}@cloudops-test.com",
            "password": "TestPassword123!"
        }

    def get_auth_headers(self, token: str) -> Dict[str, str]:
        """Get authentication headers with JWT token"""
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

    def get_cors_headers(self) -> Dict[str, str]:
        """Get expected CORS headers"""
        return {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token",
            "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS"
        }


# Global test configuration instance
test_config = TestConfig()
