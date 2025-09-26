import json
from datetime import datetime

import boto3

# Complete registry of all compliance checks
COMPLIANCE_CHECK_REGISTRY = {
    "iam_root_mfa_enabled": ["CIS-1.1", "NIST-AC-2", "PCI-8.1", "SOC2-CC6.1"],
    "iam_access_key_rotation": ["CIS-1.3", "NIST-IA-5", "PCI-8.2.4"],
    "iam_password_policy_length": ["CIS-1.5", "NIST-IA-5", "PCI-8.2.3", "SOC2-CC6.1"],
    "iam_password_policy_uppercase": ["CIS-1.6", "NIST-IA-5", "PCI-8.2.3"],
    "iam_password_policy_missing": ["CIS-1.5", "NIST-IA-5", "PCI-8.2.3", "SOC2-CC6.1"],
    "s3_bucket_public_read": ["CIS-2.1.1", "NIST-AC-3", "PCI-1.3.1", "SOC2-CC6.1"],
    "s3_bucket_ssl_requests_only": ["CIS-2.1.3", "NIST-SC-8", "PCI-4.1", "SOC2-CC6.1"],
    "s3_bucket_server_side_encryption": [
        "CIS-2.1.4",
        "NIST-SC-13",
        "PCI-3.4",
        "SOC2-CC6.1",
    ],
    "ec2_security_group_ssh_world_accessible": [
        "CIS-4.1",
        "NIST-AC-4",
        "PCI-1.3.1",
        "SOC2-CC6.1",
    ],
    "ec2_security_group_rdp_world_accessible": [
        "CIS-4.2",
        "NIST-AC-4",
        "PCI-1.3.1",
        "SOC2-CC6.1",
    ],
    "ec2_ebs_volume_encryption": ["CIS-2.2.1", "NIST-SC-13", "PCI-3.4"],
    "cloudtrail_enabled_all_regions": [
        "CIS-2.1",
        "NIST-AU-2",
        "PCI-10.2",
        "SOC2-CC7.2",
    ],
    "cloudtrail_log_file_validation": [
        "CIS-2.2",
        "NIST-AU-9",
        "PCI-10.5.2",
        "SOC2-CC7.2",
    ],
    "config_configuration_recorder_enabled": ["CIS-2.5", "NIST-CM-3", "SOC2-CC8.1"],
    "cloudwatch_log_group_cloudtrail": [
        "CIS-3.1",
        "NIST-SI-4",
        "PCI-10.6",
        "SOC2-CC7.2",
    ],
    "kms_key_rotation_enabled": ["CIS-2.8", "NIST-SC-12", "PCI-3.4", "SOC2-CC6.1"],
    "rds_instance_storage_encrypted": [
        "CIS-2.3.1",
        "NIST-SC-13",
        "PCI-3.4",
        "SOC2-CC6.1",
    ],
    "lambda_environment_variables_encrypted": ["NIST-SC-8", "SOC2-CC6.1"],
}


def run_compliance_checks(services, regions):
    """Run comprehensive compliance checks for CIS, NIST, PCI-DSS, SOC2"""
    findings = []

    for region in regions:
        for service in services:
            if service == "iam":
                findings.extend(check_iam_compliance(region))
            elif service == "s3":
                findings.extend(check_s3_compliance(region))
            elif service == "ec2":
                findings.extend(check_ec2_compliance(region))
            elif service == "cloudtrail":
                findings.extend(check_cloudtrail_compliance(region))
            elif service == "config":
                findings.extend(check_config_compliance(region))
            elif service == "cloudwatch":
                findings.extend(check_cloudwatch_compliance(region))
            elif service == "kms":
                findings.extend(check_kms_compliance(region))
            elif service == "rds":
                findings.extend(check_rds_compliance(region))
            elif service == "lambda":
                findings.extend(check_lambda_compliance(region))

    return findings


def check_iam_compliance(region):
    """IAM compliance checks for CIS, NIST, PCI-DSS, SOC2"""
    findings = []
    try:
        iam = boto3.client("iam")

        # CIS 1.1, NIST AC-2, PCI 8.1, SOC2 CC6.1: Root account MFA
        try:
            summary = iam.get_account_summary()["SummaryMap"]
            if summary.get("AccountMFAEnabled", 0) == 0:
                findings.append(
                    {
                        "check_id": "iam_root_mfa_enabled",
                        "compliance": ["CIS-1.1", "NIST-AC-2", "PCI-8.1", "SOC2-CC6.1"],
                        "severity": "CRITICAL",
                        "status": "FAIL",
                        "service_name": "iam",
                        "region": "global",
                        "resource_id": "root-account",
                        "check_title": "Root account should have MFA enabled",
                    }
                )
            else:
                findings.append(
                    {
                        "check_id": "iam_root_mfa_enabled",
                        "compliance": ["CIS-1.1", "NIST-AC-2", "PCI-8.1", "SOC2-CC6.1"],
                        "severity": "PASS",
                        "status": "PASS",
                        "service_name": "iam",
                        "region": "global",
                        "resource_id": "root-account",
                        "check_title": "Root account has MFA enabled",
                    }
                )
        except Exception as e:
            print(f"Error checking root MFA: {e}")

        # CIS 1.3, NIST IA-5, PCI 8.2.4: Access key rotation
        users = iam.list_users()["Users"]
        for user in users[:50]:
            username = user["UserName"]
            try:
                keys = iam.list_access_keys(UserName=username)["AccessKeyMetadata"]
                for key in keys:
                    age_days = (
                        datetime.now() - key["CreateDate"].replace(tzinfo=None)
                    ).days
                    if age_days > 90:
                        findings.append(
                            {
                                "check_id": "iam_access_key_rotation",
                                "compliance": ["CIS-1.3", "NIST-IA-5", "PCI-8.2.4"],
                                "severity": "MEDIUM",
                                "status": "FAIL",
                                "service_name": "iam",
                                "region": "global",
                                "resource_id": f"{username}/{key['AccessKeyId']}",
                                "check_title": "Access key should be rotated every 90 days",
                            }
                        )
            except Exception as e:
                print(f"Error checking user {username}: {e}")

        # CIS 1.5, NIST IA-5, PCI 8.2.3, SOC2 CC6.1: Password policy
        try:
            policy = iam.get_account_password_policy()["PasswordPolicy"]
            if policy.get("MinimumPasswordLength", 0) < 14:
                findings.append(
                    {
                        "check_id": "iam_password_policy_length",
                        "compliance": [
                            "CIS-1.5",
                            "NIST-IA-5",
                            "PCI-8.2.3",
                            "SOC2-CC6.1",
                        ],
                        "severity": "MEDIUM",
                        "status": "FAIL",
                        "service_name": "iam",
                        "region": "global",
                        "resource_id": "password-policy",
                        "check_title": "Password policy should require minimum 14 characters",
                    }
                )
            if not policy.get("RequireUppercaseCharacters", False):
                findings.append(
                    {
                        "check_id": "iam_password_policy_uppercase",
                        "compliance": ["CIS-1.6", "NIST-IA-5", "PCI-8.2.3"],
                        "severity": "LOW",
                        "status": "FAIL",
                        "service_name": "iam",
                        "region": "global",
                        "resource_id": "password-policy",
                        "check_title": "Password policy should require uppercase characters",
                    }
                )
        except Exception:
            findings.append(
                {
                    "check_id": "iam_password_policy_missing",
                    "compliance": ["CIS-1.5", "NIST-IA-5", "PCI-8.2.3", "SOC2-CC6.1"],
                    "severity": "HIGH",
                    "status": "FAIL",
                    "service_name": "iam",
                    "region": "global",
                    "resource_id": "password-policy",
                    "check_title": "Account password policy should be configured",
                }
            )

    except Exception as e:
        print(f"Error checking IAM: {e}")
    return findings


def check_s3_compliance(region):
    """S3 compliance checks for CIS, NIST, PCI-DSS, SOC2"""
    findings = []
    try:
        s3 = boto3.client("s3", region_name=region)
        buckets = s3.list_buckets()["Buckets"]

        for bucket in buckets[:20]:
            bucket_name = bucket["Name"]
            try:
                # CIS 2.1.1, NIST AC-3, PCI 1.3.1, SOC2 CC6.1: Public read access
                acl = s3.get_bucket_acl(Bucket=bucket_name)
                has_public_read = any(
                    grant.get("Grantee", {}).get("URI")
                    == "http://acs.amazonaws.com/groups/global/AllUsers"
                    for grant in acl.get("Grants", [])
                )
                if has_public_read:
                    findings.append(
                        {
                            "check_id": "s3_bucket_public_read",
                            "compliance": [
                                "CIS-2.1.1",
                                "NIST-AC-3",
                                "PCI-1.3.1",
                                "SOC2-CC6.1",
                            ],
                            "severity": "HIGH",
                            "status": "FAIL",
                            "service_name": "s3",
                            "region": region,
                            "resource_id": bucket_name,
                            "check_title": "S3 bucket should not allow public read access",
                        }
                    )
                else:
                    findings.append(
                        {
                            "check_id": "s3_bucket_public_read",
                            "compliance": [
                                "CIS-2.1.1",
                                "NIST-AC-3",
                                "PCI-1.3.1",
                                "SOC2-CC6.1",
                            ],
                            "severity": "PASS",
                            "status": "PASS",
                            "service_name": "s3",
                            "region": region,
                            "resource_id": bucket_name,
                            "check_title": "S3 bucket does not allow public read access",
                        }
                    )

                # CIS 2.1.3, NIST SC-8, PCI 4.1, SOC2 CC6.1: SSL/TLS enforcement
                try:
                    policy = s3.get_bucket_policy(Bucket=bucket_name)
                    policy_doc = json.loads(policy["Policy"])
                    has_ssl_only = any(
                        stmt.get("Effect") == "Deny"
                        and "aws:SecureTransport" in str(stmt.get("Condition", {}))
                        for stmt in policy_doc.get("Statement", [])
                    )
                    if not has_ssl_only:
                        findings.append(
                            {
                                "check_id": "s3_bucket_ssl_requests_only",
                                "compliance": [
                                    "CIS-2.1.3",
                                    "NIST-SC-8",
                                    "PCI-4.1",
                                    "SOC2-CC6.1",
                                ],
                                "severity": "MEDIUM",
                                "status": "FAIL",
                                "service_name": "s3",
                                "region": region,
                                "resource_id": bucket_name,
                                "check_title": "S3 bucket should enforce SSL/TLS requests only",
                            }
                        )
                except Exception:
                    findings.append(
                        {
                            "check_id": "s3_bucket_ssl_requests_only",
                            "compliance": [
                                "CIS-2.1.3",
                                "NIST-SC-8",
                                "PCI-4.1",
                                "SOC2-CC6.1",
                            ],
                            "severity": "MEDIUM",
                            "status": "FAIL",
                            "service_name": "s3",
                            "region": region,
                            "resource_id": bucket_name,
                            "check_title": "S3 bucket should enforce SSL/TLS requests only",
                        }
                    )

                # CIS 2.1.4, NIST SC-13, PCI 3.4, SOC2 CC6.1: Server-side encryption
                try:
                    s3.get_bucket_encryption(Bucket=bucket_name)
                    findings.append(
                        {
                            "check_id": "s3_bucket_server_side_encryption",
                            "compliance": [
                                "CIS-2.1.4",
                                "NIST-SC-13",
                                "PCI-3.4",
                                "SOC2-CC6.1",
                            ],
                            "severity": "PASS",
                            "status": "PASS",
                            "service_name": "s3",
                            "region": region,
                            "resource_id": bucket_name,
                            "check_title": "S3 bucket has server-side encryption enabled",
                        }
                    )
                except Exception:
                    findings.append(
                        {
                            "check_id": "s3_bucket_server_side_encryption",
                            "compliance": [
                                "CIS-2.1.4",
                                "NIST-SC-13",
                                "PCI-3.4",
                                "SOC2-CC6.1",
                            ],
                            "severity": "HIGH",
                            "status": "FAIL",
                            "service_name": "s3",
                            "region": region,
                            "resource_id": bucket_name,
                            "check_title": "S3 bucket should have server-side encryption enabled",
                        }
                    )

            except Exception as e:
                print(f"Error checking bucket {bucket_name}: {e}")
    except Exception as e:
        print(f"Error listing S3 buckets: {e}")
    return findings


def check_ec2_compliance(region):
    """EC2 compliance checks for CIS, NIST, PCI-DSS, SOC2"""
    findings = []
    try:
        ec2 = boto3.client("ec2", region_name=region)

        # CIS 4.1, NIST AC-4, PCI 1.3.1, SOC2 CC6.1: SSH access restriction
        sgs = ec2.describe_security_groups()["SecurityGroups"]
        for sg in sgs[:30]:
            for rule in sg.get("IpPermissions", []):
                from_port = rule.get("FromPort", 0)
                to_port = rule.get("ToPort", 0)

                for ip_range in rule.get("IpRanges", []):
                    if ip_range.get("CidrIp") == "0.0.0.0/0":
                        if from_port <= 22 <= to_port:
                            findings.append(
                                {
                                    "check_id": "ec2_security_group_ssh_world_accessible",
                                    "compliance": [
                                        "CIS-4.1",
                                        "NIST-AC-4",
                                        "PCI-1.3.1",
                                        "SOC2-CC6.1",
                                    ],
                                    "severity": "HIGH",
                                    "status": "FAIL",
                                    "service_name": "ec2",
                                    "region": region,
                                    "resource_id": sg["GroupId"],
                                    "check_title": "Security group should not allow SSH access from 0.0.0.0/0",
                                }
                            )
                        elif from_port <= 3389 <= to_port:
                            findings.append(
                                {
                                    "check_id": "ec2_security_group_rdp_world_accessible",
                                    "compliance": [
                                        "CIS-4.2",
                                        "NIST-AC-4",
                                        "PCI-1.3.1",
                                        "SOC2-CC6.1",
                                    ],
                                    "severity": "HIGH",
                                    "status": "FAIL",
                                    "service_name": "ec2",
                                    "region": region,
                                    "resource_id": sg["GroupId"],
                                    "check_title": "Security group should not allow RDP access from 0.0.0.0/0",
                                }
                            )

        # CIS 2.2.1, NIST SC-13, PCI 3.4: EBS encryption
        try:
            volumes = ec2.describe_volumes()["Volumes"]
            for volume in volumes[:20]:
                if not volume.get("Encrypted", False):
                    findings.append(
                        {
                            "check_id": "ec2_ebs_volume_encryption",
                            "compliance": ["CIS-2.2.1", "NIST-SC-13", "PCI-3.4"],
                            "severity": "MEDIUM",
                            "status": "FAIL",
                            "service_name": "ec2",
                            "region": region,
                            "resource_id": volume["VolumeId"],
                            "check_title": "EBS volume should be encrypted",
                        }
                    )
                else:
                    findings.append(
                        {
                            "check_id": "ec2_ebs_volume_encryption",
                            "compliance": ["CIS-2.2.1", "NIST-SC-13", "PCI-3.4"],
                            "severity": "PASS",
                            "status": "PASS",
                            "service_name": "ec2",
                            "region": region,
                            "resource_id": volume["VolumeId"],
                            "check_title": "EBS volume is encrypted",
                        }
                    )
        except Exception as e:
            print(f"Error checking EBS volumes: {e}")

    except Exception as e:
        print(f"Error checking EC2: {e}")
    return findings


def check_cloudtrail_compliance(region):
    """CloudTrail compliance checks for CIS, NIST, PCI-DSS, SOC2"""
    findings = []
    try:
        cloudtrail = boto3.client("cloudtrail", region_name=region)

        # CIS 2.1, NIST AU-2, PCI 10.2, SOC2 CC7.2: CloudTrail enabled
        trails = cloudtrail.describe_trails()["trailList"]
        multi_region_trail = any(
            trail.get("IsMultiRegionTrail", False) for trail in trails
        )

        if not multi_region_trail:
            findings.append(
                {
                    "check_id": "cloudtrail_enabled_all_regions",
                    "compliance": ["CIS-2.1", "NIST-AU-2", "PCI-10.2", "SOC2-CC7.2"],
                    "severity": "HIGH",
                    "status": "FAIL",
                    "service_name": "cloudtrail",
                    "region": region,
                    "resource_id": "cloudtrail-configuration",
                    "check_title": "CloudTrail should be enabled in all regions",
                }
            )
        else:
            findings.append(
                {
                    "check_id": "cloudtrail_enabled_all_regions",
                    "compliance": ["CIS-2.1", "NIST-AU-2", "PCI-10.2", "SOC2-CC7.2"],
                    "severity": "PASS",
                    "status": "PASS",
                    "service_name": "cloudtrail",
                    "region": region,
                    "resource_id": "cloudtrail-configuration",
                    "check_title": "CloudTrail is enabled in all regions",
                }
            )

        # CIS 2.2, NIST AU-9, PCI 10.5.2, SOC2 CC7.2: Log file validation
        for trail in trails[:10]:
            if not trail.get("LogFileValidationEnabled", False):
                findings.append(
                    {
                        "check_id": "cloudtrail_log_file_validation",
                        "compliance": [
                            "CIS-2.2",
                            "NIST-AU-9",
                            "PCI-10.5.2",
                            "SOC2-CC7.2",
                        ],
                        "severity": "MEDIUM",
                        "status": "FAIL",
                        "service_name": "cloudtrail",
                        "region": region,
                        "resource_id": trail.get("Name", "unknown"),
                        "check_title": "CloudTrail log file validation should be enabled",
                    }
                )

    except Exception as e:
        print(f"Error checking CloudTrail: {e}")
    return findings


def check_config_compliance(region):
    """AWS Config compliance checks for CIS, NIST, SOC2"""
    findings = []
    try:
        config = boto3.client("config", region_name=region)

        # CIS 2.5, NIST CM-3, SOC2 CC8.1: Config service enabled
        try:
            recorders = config.describe_configuration_recorders()[
                "ConfigurationRecorders"
            ]
            if not recorders:
                findings.append(
                    {
                        "check_id": "config_configuration_recorder_enabled",
                        "compliance": ["CIS-2.5", "NIST-CM-3", "SOC2-CC8.1"],
                        "severity": "MEDIUM",
                        "status": "FAIL",
                        "service_name": "config",
                        "region": region,
                        "resource_id": "aws-config",
                        "check_title": "AWS Config should be enabled",
                    }
                )
            else:
                findings.append(
                    {
                        "check_id": "config_configuration_recorder_enabled",
                        "compliance": ["CIS-2.5", "NIST-CM-3", "SOC2-CC8.1"],
                        "severity": "PASS",
                        "status": "PASS",
                        "service_name": "config",
                        "region": region,
                        "resource_id": "aws-config",
                        "check_title": "AWS Config is enabled",
                    }
                )
        except Exception:
            findings.append(
                {
                    "check_id": "config_configuration_recorder_enabled",
                    "compliance": ["CIS-2.5", "NIST-CM-3", "SOC2-CC8.1"],
                    "severity": "MEDIUM",
                    "status": "FAIL",
                    "service_name": "config",
                    "region": region,
                    "resource_id": "aws-config",
                    "check_title": "AWS Config should be enabled",
                }
            )

    except Exception as e:
        print(f"Error checking Config: {e}")
    return findings


def check_cloudwatch_compliance(region):
    """CloudWatch compliance checks for CIS, NIST, PCI-DSS, SOC2"""
    findings = []
    try:
        logs = boto3.client("logs", region_name=region)

        # CIS 3.1, NIST SI-4, PCI 10.6, SOC2 CC7.2: Log monitoring
        try:
            log_groups = logs.describe_log_groups()["logGroups"]
            cloudtrail_log_groups = [
                lg for lg in log_groups if "cloudtrail" in lg["logGroupName"].lower()
            ]

            if not cloudtrail_log_groups:
                findings.append(
                    {
                        "check_id": "cloudwatch_log_group_cloudtrail",
                        "compliance": [
                            "CIS-3.1",
                            "NIST-SI-4",
                            "PCI-10.6",
                            "SOC2-CC7.2",
                        ],
                        "severity": "MEDIUM",
                        "status": "FAIL",
                        "service_name": "cloudwatch",
                        "region": region,
                        "resource_id": "cloudwatch-logs",
                        "check_title": "CloudWatch should have CloudTrail log group for monitoring",
                    }
                )
            else:
                findings.append(
                    {
                        "check_id": "cloudwatch_log_group_cloudtrail",
                        "compliance": [
                            "CIS-3.1",
                            "NIST-SI-4",
                            "PCI-10.6",
                            "SOC2-CC7.2",
                        ],
                        "severity": "PASS",
                        "status": "PASS",
                        "service_name": "cloudwatch",
                        "region": region,
                        "resource_id": "cloudwatch-logs",
                        "check_title": "CloudWatch has CloudTrail log group for monitoring",
                    }
                )
        except Exception as e:
            print(f"Error checking CloudWatch logs: {e}")

    except Exception as e:
        print(f"Error checking CloudWatch: {e}")
    return findings


def check_kms_compliance(region):
    """KMS compliance checks for CIS, NIST, PCI-DSS, SOC2"""
    findings = []
    try:
        kms = boto3.client("kms", region_name=region)

        # CIS 2.8, NIST SC-12, PCI 3.4, SOC2 CC6.1: KMS key rotation
        keys = kms.list_keys()["Keys"]
        for key in keys[:20]:
            key_id = key["KeyId"]
            try:
                key_details = kms.describe_key(KeyId=key_id)["KeyMetadata"]
                if key_details.get("KeyUsage") == "ENCRYPT_DECRYPT":
                    rotation_status = kms.get_key_rotation_status(KeyId=key_id)
                    if not rotation_status.get("KeyRotationEnabled", False):
                        findings.append(
                            {
                                "check_id": "kms_key_rotation_enabled",
                                "compliance": [
                                    "CIS-2.8",
                                    "NIST-SC-12",
                                    "PCI-3.4",
                                    "SOC2-CC6.1",
                                ],
                                "severity": "MEDIUM",
                                "status": "FAIL",
                                "service_name": "kms",
                                "region": region,
                                "resource_id": key_id,
                                "check_title": "KMS key should have rotation enabled",
                            }
                        )
            except Exception as e:
                print(f"Error checking KMS key {key_id}: {e}")

    except Exception as e:
        print(f"Error checking KMS: {e}")
    return findings


def check_rds_compliance(region):
    """RDS compliance checks for CIS, NIST, PCI-DSS, SOC2"""
    findings = []
    try:
        rds = boto3.client("rds", region_name=region)

        # CIS 2.3.1, NIST SC-13, PCI 3.4, SOC2 CC6.1: RDS encryption
        instances = rds.describe_db_instances()["DBInstances"]
        for instance in instances[:10]:
            if not instance.get("StorageEncrypted", False):
                findings.append(
                    {
                        "check_id": "rds_instance_storage_encrypted",
                        "compliance": [
                            "CIS-2.3.1",
                            "NIST-SC-13",
                            "PCI-3.4",
                            "SOC2-CC6.1",
                        ],
                        "severity": "HIGH",
                        "status": "FAIL",
                        "service_name": "rds",
                        "region": region,
                        "resource_id": instance["DBInstanceIdentifier"],
                        "check_title": "RDS instance should have storage encryption enabled",
                    }
                )

    except Exception as e:
        print(f"Error checking RDS: {e}")
    return findings


def check_lambda_compliance(region):
    """Lambda compliance checks for CIS, NIST, SOC2"""
    findings = []
    try:
        lambda_client = boto3.client("lambda", region_name=region)

        # NIST SC-8, SOC2 CC6.1: Lambda environment variables encryption
        functions = lambda_client.list_functions()["Functions"]
        for function in functions[:20]:
            function_name = function["FunctionName"]
            try:
                config = lambda_client.get_function_configuration(
                    FunctionName=function_name
                )
                env_vars = config.get("Environment", {}).get("Variables", {})
                if env_vars and not config.get("KMSKeyArn"):
                    findings.append(
                        {
                            "check_id": "lambda_environment_variables_encrypted",
                            "compliance": ["NIST-SC-8", "SOC2-CC6.1"],
                            "severity": "MEDIUM",
                            "status": "FAIL",
                            "service_name": "lambda",
                            "region": region,
                            "resource_id": function_name,
                            "check_title": "Lambda function environment variables should be encrypted",
                        }
                    )
            except Exception as e:
                print(f"Error checking Lambda function {function_name}: {e}")

    except Exception as e:
        print(f"Error checking Lambda: {e}")
    return findings
