import logging
import os
from datetime import datetime, timedelta, timezone

import boto3
import requests

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
dynamodb = boto3.resource("dynamodb")
lambda_client = boto3.client("lambda")

eol_database_table_name = os.environ.get(
    "EOL_DATABASE_TABLE", "cloudops-assistant-eol-database"
)
eol_database_table = dynamodb.Table(eol_database_table_name)


def lambda_handler(event, context):
    """EOL Scheduler - Update EOL database and trigger scans"""
    try:
        logger.info("Starting EOL scheduler")

        # Update EOL database with latest data
        update_eol_database()

        logger.info("EOL scheduler completed successfully")
        return {"statusCode": 200, "body": "EOL scheduler completed"}

    except Exception as e:
        logger.error(f"EOL scheduler error: {str(e)}")
        return {"statusCode": 500, "body": f"Error: {str(e)}"}


def update_eol_database():
    """Update EOL database with latest data from endoflife.date"""
    try:
        # List of technologies to track
        technologies = [
            "python",
            "nodejs",
            "java",
            "go",
            "ruby",
            "php",
            "ubuntu",
            "debian",
            "alpine",
            "centos",
            "rhel",
            "postgresql",
            "mysql",
            "redis",
            "mongodb",
            "elasticsearch",
            "docker",
            "kubernetes",
            "terraform",
            "ansible",
        ]

        for tech in technologies:
            try:
                update_technology_eol_data(tech)
            except Exception as e:
                logger.error(f"Error updating {tech}: {str(e)}")
                continue

        logger.info(f"Updated EOL data for {len(technologies)} technologies")

    except Exception as e:
        logger.error(f"Error updating EOL database: {str(e)}")


def update_technology_eol_data(tech_name):
    """Update EOL data for a specific technology"""
    try:
        url = f"https://endoflife.date/api/{tech_name}.json"
        response = requests.get(url, timeout=30)

        if response.status_code != 200:
            logger.warning(
                f"Failed to fetch EOL data for {tech_name}: {response.status_code}"
            )
            return

        data = response.json()

        for version_info in data[:10]:  # Limit to 10 most recent versions
            cycle = version_info.get("cycle")
            eol_date = version_info.get("eol")

            if not cycle or not eol_date or eol_date is False:
                continue

            # Create EOL record
            eol_id = f"language:{tech_name}:{cycle}"

            # Check if record exists and is recent
            try:
                existing = eol_database_table.get_item(Key={"eol_id": eol_id})
                if "Item" in existing:
                    last_updated = existing["Item"].get("last_updated", "")
                    if last_updated:
                        last_update_time = datetime.fromisoformat(
                            last_updated.replace("Z", "+00:00")
                        )
                        if (datetime.now(timezone.utc) - last_update_time).days < 7:
                            continue  # Skip if updated within last week
            except Exception:
                pass

            # Store/update EOL data

            # Sanitize inputs to prevent NoSQL injection (CWE-89)
            import re

            # Sanitize string inputs to remove dangerous characters
            safe_eol_id = re.sub(r"[^a-zA-Z0-9:._-]", "", str(eol_id))[:100]
            safe_tech_name = re.sub(r"[^a-zA-Z0-9._-]", "", str(tech_name))[:50]
            safe_version = re.sub(r"[^a-zA-Z0-9._-]", "", str(cycle))[:20]

            # Validate required fields
            if not safe_eol_id or not safe_tech_name or not safe_version:
                logger.warning(f"Skipping invalid record for {tech_name} {cycle}")
                continue

            sanitized_record = {
                "eol_id": safe_eol_id,
                "technology_type": "language",  # Fixed value, no injection risk
                "name": safe_tech_name,
                "version": safe_version,
                "eol_date": str(eol_date)[:50] if eol_date else None,  # Limit length
                "support_date": str(version_info.get("support", ""))[:50]
                if version_info.get("support")
                else None,
                "release_date": str(version_info.get("releaseDate", ""))[:50]
                if version_info.get("releaseDate")
                else None,
                "latest": re.sub(
                    r"[^a-zA-Z0-9._-]", "", str(version_info.get("latest", ""))
                )[:20]
                if version_info.get("latest")
                else None,
                "lts": bool(version_info.get("lts", False)),
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "ttl": int((datetime.now() + timedelta(days=90)).timestamp()),
            }

            # Use parameterized DynamoDB operation to prevent injection
            eol_database_table.put_item(Item=sanitized_record)
            logger.info(f"Updated EOL data for {tech_name} {cycle}")

    except Exception as e:
        logger.error(f"Error updating {tech_name} EOL data: {str(e)}")


def calculate_risk_level(eol_date):
    """Calculate risk level based on EOL date"""
    try:
        if isinstance(eol_date, bool) and not eol_date:
            return "low"  # No EOL date set

        eol_datetime = datetime.fromisoformat(str(eol_date).replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        days_until_eol = (eol_datetime - now).days

        if days_until_eol < 0:
            return "critical"  # Already EOL
        elif days_until_eol < 90:
            return "high"  # EOL within 3 months
        elif days_until_eol < 365:
            return "medium"  # EOL within 1 year
        else:
            return "low"  # EOL more than 1 year away

    except Exception:
        return "low"
