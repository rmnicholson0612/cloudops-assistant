import json
import os
import sys
from datetime import datetime

import boto3

# Add paths before importing local modules
sys.path.append("/opt/python")
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Local imports after path setup
from auth_utils import verify_jwt_token  # noqa: E402
from compliance_checks import run_compliance_checks  # noqa: E402


def lambda_handler(event, context):
    try:
        path = event.get("path", "")
        method = event.get("httpMethod", "")

        # Handle CORS preflight requests
        if method == "OPTIONS":
            return {"statusCode": 200, "headers": get_cors_headers(), "body": ""}

        # Verify authentication for non-OPTIONS requests
        user_info, auth_error = verify_jwt_token(event)
        if auth_error:
            return {
                "statusCode": 401,
                "headers": get_cors_headers(),
                "body": json.dumps({"error": auth_error}),
            }

        if path == "/security/scan" and method == "POST":
            return handle_security_scan(event, user_info)
        elif path == "/security/findings" and method == "GET":
            return handle_get_findings(event, user_info)
        elif path == "/security/compliance" and method == "GET":
            return handle_get_compliance(event, user_info)
        elif path == "/security/accounts" and method == "GET":
            return handle_get_accounts(event, user_info)
        else:
            return {
                "statusCode": 404,
                "headers": get_cors_headers(),
                "body": json.dumps({"error": "Endpoint not found"}),
            }

    except Exception as e:
        return {
            "statusCode": 500,
            "headers": get_cors_headers(),
            "body": json.dumps({"error": str(e)}),
        }


def get_cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": (
            "Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token"
        ),
        "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
    }


def handle_security_scan(event, user_info):
    # Parse request body
    body = json.loads(event.get("body", "{}"))
    services = body.get("services", ["s3", "iam", "ec2"])
    regions = body.get("regions", ["us-east-1"])

    # Run security scan
    scan_results = run_security_scan(services, regions)

    # Store results with user context
    findings_count = store_scan_results(scan_results, services, regions, user_info)

    return {
        "statusCode": 200,
        "headers": get_cors_headers(),
        "body": json.dumps(
            {
                "scan_id": f"scan_{datetime.now().isoformat()}",
                "services": services,
                "regions": regions,
                "findings_count": findings_count,
            }
        ),
    }


def handle_get_findings(event, user_info):
    # Get stored findings from DynamoDB for this user
    findings = get_stored_findings(user_info)

    return {
        "statusCode": 200,
        "headers": get_cors_headers(),
        "body": json.dumps(findings),
    }


def handle_get_compliance(event, user_info):
    from compliance_checks import COMPLIANCE_CHECK_REGISTRY

    # Get compliance summary from stored findings
    findings = get_stored_findings(user_info)

    # Track which checks actually ran
    executed_checks = set()
    framework_checks = {}

    for finding in findings:
        check_id = finding.get("check_id", "unknown")
        executed_checks.add(check_id)
        severity = finding.get("severity", "INFO").lower()
        status = finding.get("status", "UNKNOWN")

        for compliance in finding.get("compliance", []):
            framework = compliance.split("-")[0]
            if framework not in framework_checks:
                framework_checks[framework] = {}

            # Track unique check with worst severity/status
            if check_id not in framework_checks[framework]:
                framework_checks[framework][check_id] = {
                    "severity": severity,
                    "status": status,
                }
            else:
                # Keep worst severity for this check
                current = framework_checks[framework][check_id]
                severity_order = {
                    "critical": 4,
                    "high": 3,
                    "medium": 2,
                    "low": 1,
                    "pass": 0,
                }
                if severity_order.get(severity, 0) > severity_order.get(
                    current["severity"], 0
                ):
                    framework_checks[framework][check_id] = {
                        "severity": severity,
                        "status": status,
                    }

    # Build complete compliance summary with NOT_APPLICABLE
    compliance_summary = {}

    # Get all frameworks from registry
    all_frameworks = set()
    for check_id, frameworks in COMPLIANCE_CHECK_REGISTRY.items():
        for framework_check in frameworks:
            framework = framework_check.split("-")[0]
            all_frameworks.add(framework)

    # Initialize all frameworks
    for framework in all_frameworks:
        compliance_summary[framework] = {
            "total": 0,
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "not_applicable": 0,
        }

    # Add all checks from registry
    for check_id, frameworks in COMPLIANCE_CHECK_REGISTRY.items():
        for framework_check in frameworks:
            framework = framework_check.split("-")[0]
            compliance_summary[framework]["total"] += 1

            if check_id in executed_checks and check_id in framework_checks.get(
                framework, {}
            ):
                # Check was executed
                severity = framework_checks[framework][check_id]["severity"]
                if severity in ["critical", "high", "medium", "low"]:
                    compliance_summary[framework][severity] += 1
            else:
                # Check was not executed - mark as NOT_APPLICABLE
                compliance_summary[framework]["not_applicable"] += 1

    return {
        "statusCode": 200,
        "headers": get_cors_headers(),
        "body": json.dumps(compliance_summary),
    }


def handle_get_accounts(event, user_info):
    # Get account summary from stored findings
    findings = get_stored_findings(user_info)

    accounts_summary = {}

    for finding in findings:
        account_id = finding.get("account_id", "unknown")
        severity = finding.get("severity", "INFO").lower()

        if account_id not in accounts_summary:
            accounts_summary[account_id] = {
                "total": 0,
                "critical": 0,
                "high": 0,
                "medium": 0,
                "low": 0,
                "regions": set(),
                "services": set(),
            }

        accounts_summary[account_id]["total"] += 1
        if severity in accounts_summary[account_id]:
            accounts_summary[account_id][severity] += 1

        accounts_summary[account_id]["regions"].add(finding.get("region", "unknown"))
        accounts_summary[account_id]["services"].add(finding.get("service", "unknown"))

    # Convert sets to lists for JSON serialization
    for account_id in accounts_summary:
        accounts_summary[account_id]["regions"] = list(
            accounts_summary[account_id]["regions"]
        )
        accounts_summary[account_id]["services"] = list(
            accounts_summary[account_id]["services"]
        )

    return {
        "statusCode": 200,
        "headers": get_cors_headers(),
        "body": json.dumps(accounts_summary),
    }


def get_stored_findings(user_info):
    try:
        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.Table(os.environ["SECURITY_FINDINGS_TABLE"])

        # Get today's findings for this user
        today = datetime.now().date()
        user_id = user_info.get("user_id", "unknown")
        response = table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key("PK").eq(
                f"user_{user_id}_scan_{today}"
            )
        )

        findings = []
        for item in response.get("Items", []):
            findings.append(
                {
                    "status": item.get("status", "UNKNOWN"),
                    "severity": item.get("severity", "INFO"),
                    "service": item.get("service", "unknown"),
                    "region": item.get("region", "unknown"),
                    "account_id": item.get("account_id", "unknown"),
                    "description": item.get("description", "Security finding"),
                    "resource_id": item.get("resource_id", "unknown"),
                    "timestamp": item.get("timestamp", ""),
                    "compliance": item.get("compliance", []),
                    "check_id": item.get("check_id", "unknown"),
                }
            )

        return findings

    except Exception as e:
        print(f"Error getting findings: {e}")
        return []


def run_security_scan(services, regions):
    """Run comprehensive compliance checks for CIS, NIST, PCI-DSS, SOC2"""
    findings = run_compliance_checks(services, regions)
    return {"findings": findings}


def store_scan_results(scan_results, services, regions, user_info):
    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(os.environ["SECURITY_FINDINGS_TABLE"])

    # Get AWS account ID
    try:
        sts = boto3.client("sts")
        account_id = sts.get_caller_identity()["Account"]
    except Exception:
        account_id = "unknown"

    findings = scan_results.get("findings", [])
    findings_count = 0
    user_id = user_info.get("user_id", "unknown")

    for finding in findings:
        findings_count += 1
        # Store both PASS and FAIL results
        status = finding.get("status", "UNKNOWN")
        severity = finding.get("severity", "INFO") if status == "FAIL" else "PASS"

        table.put_item(
            Item={
                "PK": f"user_{user_id}_scan_{datetime.now().date()}",
                "SK": f"finding_{findings_count}",
                "status": status,
                "severity": severity,
                "service": finding.get("service_name", "unknown"),
                "region": finding.get("region", "unknown"),
                "account_id": account_id,
                "resource_id": finding.get("resource_id", "unknown"),
                "description": finding.get("check_title", "Security finding"),
                "compliance": finding.get("compliance", []),
                "check_id": finding.get("check_id", "unknown"),
                "timestamp": datetime.now().isoformat(),
                "TTL": int(datetime.now().timestamp()) + 2592000,
            }
        )

    return findings_count
