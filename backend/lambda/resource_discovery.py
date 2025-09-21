import json
import logging
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import boto3

try:
    from auth_utils import auth_required
except ImportError:
    # Mock auth_required for testing
    def auth_required(func):
        def wrapper(event, context):
            # Check if user_info exists in event for testing
            if "user_info" not in event:
                return {
                    "statusCode": 401,
                    "headers": {
                        "Content-Type": "application/json",
                        "Access-Control-Allow-Origin": "*",
                    },
                    "body": json.dumps({"error": "Unauthorized"}),
                }
            return func(event, context)

        return wrapper


logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
dynamodb = boto3.resource("dynamodb")
discovery_table = dynamodb.Table("cloudops-assistant-resource-discovery")


def lambda_handler(event, context):
    """Handle resource discovery requests"""
    logger.info(f"Received event: {json.dumps(event)}")

    if event.get("httpMethod") == "OPTIONS":
        return cors_response()

    try:
        return _authenticated_handler(event, context)
    except Exception as e:
        logger.error(f"Lambda handler error: {str(e)}")
        return error_response(f"Handler error: {str(e)}", 500)


@auth_required
def _authenticated_handler(event, context):
    try:
        path = event.get("path", "")
        method = event.get("httpMethod", "")

        if method == "POST" and "/discovery/scan" in path:
            return start_discovery_scan(event)
        elif method == "GET" and "/discovery/status/" in path:
            return get_scan_status(event)
        elif method == "POST" and "/discovery/approve/" in path:
            return approve_service(event)
        elif method == "POST" and "/discovery/reject/" in path:
            return reject_service(event)
        elif method == "GET" and "/discovery/services" in path:
            return get_discovered_services(event)
        elif method == "GET" and "/discovery/resources" in path:
            return get_all_resources(event)
        else:
            return error_response("Invalid endpoint", 404)

    except Exception as e:
        logger.error(f"Resource discovery error: {str(e)}")
        return error_response("Internal server error")


def start_discovery_scan(event):
    """Start a new resource discovery scan"""
    try:
        body_str = event.get("body") or "{}"
        body = json.loads(body_str) if body_str else {}

        regions = body.get("regions", ["us-east-1"])
        resource_types = body.get("resource_types", ["EC2", "Lambda", "RDS", "S3"])

        # Validate inputs
        if not isinstance(regions, list) or not regions:
            return error_response("Invalid regions specified")

        if not isinstance(resource_types, list) or not resource_types:
            return error_response("Invalid resource types specified")

        # Generate scan ID
        scan_id = f"scan-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"

        # Start the discovery process
        scan_result = perform_resource_discovery(regions, resource_types, scan_id)

        return success_response(
            {
                "scan_id": scan_id,
                "status": "completed",
                "total_resources": scan_result["total_resources"],
                "total_services": scan_result["total_services"],
                "total_cost": scan_result["total_cost"],
                "scan_time": scan_result["scan_time"],
                "service_suggestions": scan_result["service_suggestions"],
            }
        )

    except Exception as e:
        logger.error(f"Error starting discovery scan: {str(e)}")
        return error_response("Failed to start discovery scan")


def perform_resource_discovery(regions, resource_types, scan_id):
    """Perform the actual resource discovery"""
    start_time = datetime.now(timezone.utc)
    all_resources = []

    try:
        logger.info(
            f"Starting resource discovery for regions: {regions}, types: {resource_types}"
        )

        # Discover resources across all specified regions
        for region in regions:
            logger.info(f"Scanning region: {region}")
            region_resources = discover_resources_in_region(region, resource_types)
            logger.info(f"Found {len(region_resources)} resources in {region}")
            all_resources.extend(region_resources)

        logger.info(f"Total resources discovered: {len(all_resources)}")

        # Get cost data for discovered resources
        cost_data = get_resource_costs(all_resources)

        # Use AI to group resources into services
        service_suggestions = generate_service_suggestions(all_resources, cost_data)

        # Calculate totals
        total_cost = sum(
            float(service.get("monthly_cost", 0)) for service in service_suggestions
        )
        scan_time = (datetime.now(timezone.utc) - start_time).total_seconds()

        # Store scan results (convert floats to Decimal for DynamoDB)
        store_scan_results(
            scan_id,
            {
                "resources": all_resources,
                "service_suggestions": convert_floats_to_decimal(service_suggestions),
                "total_resources": len(all_resources),
                "total_services": len(service_suggestions),
                "total_cost": Decimal(str(total_cost)),
                "scan_time": Decimal(str(scan_time)),
                "regions": regions,
                "resource_types": resource_types,
            },
        )

        logger.info(
            f"Scan completed: {len(all_resources)} resources, {len(service_suggestions)} services"
        )

        return {
            "total_resources": len(all_resources),
            "total_services": len(service_suggestions),
            "total_cost": total_cost,
            "scan_time": int(scan_time),
            "service_suggestions": service_suggestions,
        }

    except Exception as e:
        logger.error(f"Discovery scan failed: {str(e)}")
        raise


def discover_resources_in_region(region, resource_types):
    """Discover resources in a specific AWS region"""
    resources = []

    try:
        # EC2 Instances
        if "EC2" in resource_types:
            resources.extend(discover_ec2_instances(region))

        # Lambda Functions
        if "Lambda" in resource_types:
            resources.extend(discover_lambda_functions(region))

        # RDS Databases
        if "RDS" in resource_types:
            resources.extend(discover_rds_instances(region))

        # S3 Buckets (global service, only scan once)
        if "S3" in resource_types and region == "us-east-1":
            resources.extend(discover_s3_buckets())

        # Load Balancers
        if "ALB" in resource_types:
            resources.extend(discover_load_balancers(region))

        # VPC Resources
        if "VPC" in resource_types:
            resources.extend(discover_vpc_resources(region))

    except Exception as e:
        logger.error(f"Error discovering resources in {region}: {str(e)}")

    return resources


def discover_ec2_instances(region):
    """Discover EC2 instances in a region"""
    try:
        ec2 = boto3.client("ec2", region_name=region)
        response = ec2.describe_instances(
            MaxResults=100
        )  # Limit results for performance

        instances = []
        for reservation in response.get("Reservations", []):
            for instance in reservation.get("Instances", []):
                if instance["State"]["Name"] != "terminated":
                    instances.append(
                        {
                            "name": get_resource_name(instance.get("Tags", []))
                            or instance["InstanceId"],
                            "type": "EC2",
                            "id": instance["InstanceId"],
                            "region": region,
                            "tags": {
                                tag["Key"]: tag["Value"]
                                for tag in instance.get("Tags", [])
                            },
                            "instance_type": instance.get("InstanceType"),
                            "state": instance["State"]["Name"],
                            "vpc_id": instance.get("VpcId"),
                            "subnet_id": instance.get("SubnetId"),
                        }
                    )

        return instances
    except Exception as e:
        logger.error(f"Error discovering EC2 instances in {region}: {str(e)}")
        # Return empty list but don't fail the entire scan
        return []


def discover_lambda_functions(region):
    """Discover Lambda functions in a region"""
    try:
        lambda_client = boto3.client("lambda", region_name=region)
        response = lambda_client.list_functions(
            MaxItems=100
        )  # Limit results for performance

        functions = []
        for func in response.get("Functions", []):
            # Get tags for the function
            try:
                tags_response = lambda_client.list_tags(Resource=func["FunctionArn"])
                tags = tags_response.get("Tags", {})
            except Exception:
                tags = {}

            functions.append(
                {
                    "name": func["FunctionName"],
                    "type": "Lambda",
                    "id": func["FunctionArn"],
                    "region": region,
                    "tags": tags,
                    "runtime": func.get("Runtime"),
                    "memory_size": func.get("MemorySize"),
                    "timeout": func.get("Timeout"),
                }
            )

        return functions
    except Exception as e:
        logger.error(f"Error discovering Lambda functions in {region}: {str(e)}")
        return []


def discover_rds_instances(region):
    """Discover RDS instances in a region"""
    try:
        rds = boto3.client("rds", region_name=region)
        response = rds.describe_db_instances()

        instances = []
        for db in response.get("DBInstances", []):
            # Get tags for the DB instance
            try:
                tags_response = rds.list_tags_for_resource(
                    ResourceName=db["DBInstanceArn"]
                )
                tags = {
                    tag["Key"]: tag["Value"] for tag in tags_response.get("TagList", [])
                }
            except Exception:
                tags = {}

            instances.append(
                {
                    "name": db["DBInstanceIdentifier"],
                    "type": "RDS",
                    "id": db["DBInstanceArn"],
                    "region": region,
                    "tags": tags,
                    "engine": db.get("Engine"),
                    "instance_class": db.get("DBInstanceClass"),
                    "status": db.get("DBInstanceStatus"),
                    "vpc_id": (
                        db.get("DbSubnetGroup", {}).get("VpcId")
                        if db.get("DbSubnetGroup")
                        else None
                    ),
                }
            )

        return instances
    except Exception as e:
        logger.error(f"Error discovering RDS instances in {region}: {str(e)}")
        return []


def discover_s3_buckets():
    """Discover S3 buckets (global service)"""
    try:
        s3 = boto3.client("s3")
        logger.info("Starting S3 bucket discovery...")

        # Check if we have permission to list buckets
        try:
            response = s3.list_buckets()
        except Exception as e:
            if "AccessDenied" in str(e):
                logger.warning(
                    "No permission to list S3 buckets, skipping S3 discovery"
                )
                return []
            raise

        logger.info(f"Found {len(response.get('Buckets', []))} S3 buckets")

        buckets = []
        for bucket in response.get("Buckets", []):
            logger.info(f"Processing bucket: {bucket['Name']}")
            # Get bucket tags
            try:
                tags_response = s3.get_bucket_tagging(Bucket=bucket["Name"])
                tags = {
                    tag["Key"]: tag["Value"] for tag in tags_response.get("TagSet", [])
                }
            except Exception as e:
                logger.info(f"No tags for bucket {bucket['Name']}: {str(e)}")
                tags = {}

            # Get bucket region
            try:
                location_response = s3.get_bucket_location(Bucket=bucket["Name"])
                region = location_response.get("LocationConstraint") or "us-east-1"
            except Exception as e:
                logger.info(
                    f"Could not get region for bucket {bucket['Name']}: {str(e)}"
                )
                region = "us-east-1"

            buckets.append(
                {
                    "name": bucket["Name"],
                    "type": "S3",
                    "id": f"arn:aws:s3:::{bucket['Name']}",
                    "region": region,
                    "tags": tags,
                    "creation_date": bucket["CreationDate"].isoformat(),
                }
            )

        logger.info(f"Successfully processed {len(buckets)} S3 buckets")
        return buckets
    except Exception as e:
        logger.error(f"Error discovering S3 buckets: {str(e)}")
        return []


def discover_load_balancers(region):
    """Discover Application Load Balancers in a region"""
    try:
        elbv2 = boto3.client("elbv2", region_name=region)
        response = elbv2.describe_load_balancers()

        load_balancers = []
        for lb in response.get("LoadBalancers", []):
            # Get tags for the load balancer
            try:
                tags_response = elbv2.describe_tags(
                    ResourceArns=[lb["LoadBalancerArn"]]
                )
                tags = {}
                for tag_desc in tags_response.get("TagDescriptions", []):
                    for tag in tag_desc.get("Tags", []):
                        tags[tag["Key"]] = tag["Value"]
            except Exception:
                tags = {}

            load_balancers.append(
                {
                    "name": lb["LoadBalancerName"],
                    "type": "ALB",
                    "id": lb["LoadBalancerArn"],
                    "region": region,
                    "tags": tags,
                    "scheme": lb.get("Scheme"),
                    "state": lb.get("State", {}).get("Code"),
                    "vpc_id": lb.get("VpcId"),
                }
            )

        return load_balancers
    except Exception as e:
        logger.error(f"Error discovering load balancers in {region}: {str(e)}")
        return []


def discover_vpc_resources(region):
    """Discover VPC resources in a region"""
    try:
        ec2 = boto3.client("ec2", region_name=region)

        resources = []

        # VPCs
        vpcs_response = ec2.describe_vpcs()
        for vpc in vpcs_response.get("Vpcs", []):
            resources.append(
                {
                    "name": get_resource_name(vpc.get("Tags", [])) or vpc["VpcId"],
                    "type": "VPC",
                    "id": vpc["VpcId"],
                    "region": region,
                    "tags": {tag["Key"]: tag["Value"] for tag in vpc.get("Tags", [])},
                    "cidr_block": vpc.get("CidrBlock"),
                    "state": vpc.get("State"),
                }
            )

        # Security Groups
        sgs_response = ec2.describe_security_groups()
        for sg in sgs_response.get("SecurityGroups", []):
            if sg["GroupName"] != "default":  # Skip default security groups
                resources.append(
                    {
                        "name": sg.get("GroupName", sg["GroupId"]),
                        "type": "SecurityGroup",
                        "id": sg["GroupId"],
                        "region": region,
                        "tags": {
                            tag["Key"]: tag["Value"] for tag in sg.get("Tags", [])
                        },
                        "vpc_id": sg.get("VpcId"),
                        "description": sg.get("Description"),
                    }
                )

        return resources
    except Exception as e:
        logger.error(f"Error discovering VPC resources in {region}: {str(e)}")
        return []


def get_resource_name(tags):
    """Extract resource name from tags"""
    for tag in tags:
        if tag.get("Key") == "Name":
            return tag.get("Value")
    return None


def get_resource_costs(resources):
    """Get cost data for discovered resources"""
    try:
        # Use Cost Explorer to get resource costs
        ce = boto3.client("ce")

        # Get costs for the last 30 days
        end_date = datetime.now(timezone.utc).date()
        start_date = end_date - timedelta(days=30)

        response = ce.get_cost_and_usage(
            TimePeriod={
                "Start": start_date.strftime("%Y-%m-%d"),
                "End": end_date.strftime("%Y-%m-%d"),
            },
            Granularity="MONTHLY",
            Metrics=["BlendedCost"],
            GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
        )

        # Create a mapping of service to cost
        service_costs = {}
        for result in response.get("ResultsByTime", []):
            for group in result.get("Groups", []):
                service = group["Keys"][0]
                cost = float(group["Metrics"]["BlendedCost"]["Amount"])
                service_costs[service] = cost

        return service_costs
    except Exception as e:
        logger.error(f"Error getting resource costs: {str(e)}")
        return {}


def generate_service_suggestions(resources, cost_data):
    """Use AI to generate service grouping suggestions"""
    try:
        # Group resources by common patterns
        service_groups = {}

        for resource in resources:
            # Try to extract service name from resource name or tags
            service_name = extract_service_name(resource)

            if service_name not in service_groups:
                service_groups[service_name] = {
                    "name": service_name,
                    "resources": [],
                    "confidence": 0,
                    "monthly_cost": 0,
                }

            service_groups[service_name]["resources"].append(
                {
                    "name": resource["name"],
                    "type": resource["type"],
                    "id": resource["id"],
                }
            )

        # Calculate confidence scores and costs
        suggestions = []
        for service_name, group in service_groups.items():
            # Calculate confidence based on naming consistency and tags
            confidence = calculate_confidence_score(group["resources"], resources)

            # Calculate estimated monthly cost
            monthly_cost = estimate_service_cost(group["resources"], cost_data)

            suggestions.append(
                {
                    "id": f"service-{len(suggestions)}",
                    "name": service_name,
                    "resources": group["resources"],
                    "resource_count": len(group["resources"]),
                    "confidence": confidence,
                    "monthly_cost": float(
                        monthly_cost
                    ),  # Keep as float for JSON serialization
                }
            )

        # Sort by confidence score
        suggestions.sort(key=lambda x: x["confidence"], reverse=True)

        return suggestions[:10]  # Return top 10 suggestions

    except Exception as e:
        logger.error(f"Error generating service suggestions: {str(e)}")
        return []


def extract_service_name(resource):
    """Extract service name from resource name or tags"""
    # Check for Service tag first
    if "Service" in resource.get("tags", {}):
        return resource["tags"]["Service"]

    # Try to extract from resource name
    name = resource.get("name", "")

    # Common patterns: service-component-env, service_component, etc.
    patterns = [
        r"^([a-zA-Z]+)[-_]",  # service-something or service_something
        r"^([a-zA-Z]+)",  # just the first word
    ]

    for pattern in patterns:
        match = re.match(pattern, name)
        if match:
            service_name = match.group(1).lower()
            # Capitalize first letter
            return service_name.capitalize() + " Service"

    # Try to extract from first word of name
    first_word = name.split("-")[0].split("_")[0]
    if first_word and len(first_word) > 2 and first_word.isalpha():
        return first_word.capitalize() + " Service"

    # Fallback based on resource type
    return f"{resource['type']} Service"


def calculate_confidence_score(group_resources, all_resources):
    """Calculate confidence score for a service grouping"""
    if len(group_resources) == 1:
        return 60  # Low confidence for single resources

    # Check naming consistency
    names = [r["name"] for r in group_resources]
    common_prefix = find_common_prefix(names)

    if len(common_prefix) > 3:
        return min(95, 70 + len(common_prefix) * 3)
    elif len(group_resources) > 3:
        return 85
    else:
        return 75


def find_common_prefix(strings):
    """Find common prefix among strings"""
    if not strings:
        return ""

    prefix = strings[0]
    for string in strings[1:]:
        while not string.startswith(prefix):
            prefix = prefix[:-1]
            if not prefix:
                break

    return prefix


def estimate_service_cost(resources, cost_data):
    """Estimate monthly cost for a service based on its resources"""
    total_cost = 0

    # Map resource types to AWS service names
    service_mapping = {
        "EC2": "Amazon Elastic Compute Cloud - Compute",
        "Lambda": "AWS Lambda",
        "RDS": "Amazon Relational Database Service",
        "S3": "Amazon Simple Storage Service",
        "ALB": "Amazon Elastic Load Balancing",
    }

    resource_counts = {}
    for resource in resources:
        resource_type = resource["type"]
        resource_counts[resource_type] = resource_counts.get(resource_type, 0) + 1

    # Estimate costs based on resource counts and actual cost data
    for resource_type, count in resource_counts.items():
        service_name = service_mapping.get(resource_type)
        if service_name and service_name in cost_data:
            # Distribute service cost proportionally
            service_cost = cost_data[service_name]
            # Simple estimation: divide by estimated total resources of this type
            estimated_cost_per_resource = service_cost / max(count, 1)
            total_cost += estimated_cost_per_resource * count

    return round(total_cost, 2)


def convert_floats_to_decimal(obj):
    """Convert float values to Decimal for DynamoDB compatibility"""
    if isinstance(obj, float):
        return Decimal(str(obj))
    elif isinstance(obj, dict):
        return {k: convert_floats_to_decimal(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_floats_to_decimal(item) for item in obj]
    else:
        return obj


def store_scan_results(scan_id, results):
    """Store scan results in DynamoDB"""
    try:
        discovery_table.put_item(
            Item={
                "scan_id": scan_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "completed",
                "results": results,
                "ttl": int(
                    (datetime.now(timezone.utc) + timedelta(days=30)).timestamp()
                ),
            }
        )
    except Exception as e:
        logger.error(f"Error storing scan results: {str(e)}")


def get_scan_status(event):
    """Get status of a discovery scan"""
    try:
        # Extract scan_id from path
        path = event.get("path", "")
        scan_id = None

        # Try pathParameters first
        if event.get("pathParameters"):
            scan_id = event["pathParameters"].get("scan_id")

        # If not found, extract from path
        if not scan_id and "/discovery/status/" in path:
            scan_id = path.split("/discovery/status/")[-1]

        if not scan_id:
            return error_response("Missing scan_id parameter")

        # For this implementation, scans complete immediately
        # In a real implementation, you might have async processing
        return success_response(
            {"scan_id": scan_id, "status": "completed", "progress": 100}
        )

    except Exception as e:
        logger.error(f"Error getting scan status: {str(e)}")
        return error_response("Failed to get scan status")


def approve_service(event):
    """Approve a service suggestion"""
    try:
        # Extract service_id from path
        path = event.get("path", "")
        service_id = None

        # Try pathParameters first
        if event.get("pathParameters"):
            service_id = event["pathParameters"].get("service_id")

        # If not found, extract from path
        if not service_id and "/discovery/approve/" in path:
            service_id = path.split("/discovery/approve/")[-1]

        if not service_id:
            return error_response("Missing service_id parameter")

        # In a real implementation, you would:
        # 1. Move the service from suggestions to approved services
        # 2. Update the service registry
        # 3. Set up monitoring/alerting for the service

        return success_response(
            {"message": "Service approved successfully", "service_id": service_id}
        )

    except Exception as e:
        logger.error(f"Error approving service: {str(e)}")
        return error_response("Failed to approve service")


def reject_service(event):
    """Reject a service suggestion"""
    try:
        # Extract service_id from path
        path = event.get("path", "")
        service_id = None

        # Try pathParameters first
        if event.get("pathParameters"):
            service_id = event["pathParameters"].get("service_id")

        # If not found, extract from path
        if not service_id and "/discovery/reject/" in path:
            service_id = path.split("/discovery/reject/")[-1]

        if not service_id:
            return error_response("Missing service_id parameter")

        # In a real implementation, you would remove the suggestion

        return success_response(
            {"message": "Service rejected", "service_id": service_id}
        )

    except Exception as e:
        logger.error(f"Error rejecting service: {str(e)}")
        return error_response("Failed to reject service")


def get_discovered_services(event):
    """Get list of discovered/approved services"""
    try:
        # Get latest scan results (organization-wide)
        try:
            response = discovery_table.scan(
                FilterExpression="#status = :status",
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={":status": "completed"},
                Limit=10,
            )

            if response["Items"]:
                # Sort by timestamp to get latest
                items = sorted(
                    response["Items"],
                    key=lambda x: x.get("timestamp", ""),
                    reverse=True,
                )
                latest_scan = items[0]
                services = latest_scan.get("results", {}).get("service_suggestions", [])
                return success_response({"services": services, "total": len(services)})
        except Exception as e:
            logger.error(f"Error querying scan results: {str(e)}")

        return success_response({"services": [], "total": 0})

    except Exception as e:
        logger.error(f"Error getting discovered services: {str(e)}")
        return error_response("Failed to get discovered services")


def get_all_resources(event):
    """Get list of all discovered resources"""
    try:
        # Get latest scan results (organization-wide)
        try:
            response = discovery_table.scan(
                FilterExpression="#status = :status",
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={":status": "completed"},
                Limit=10,
            )

            if response["Items"]:
                # Sort by timestamp to get latest
                items = sorted(
                    response["Items"],
                    key=lambda x: x.get("timestamp", ""),
                    reverse=True,
                )
                latest_scan = items[0]
                resources = latest_scan.get("results", {}).get("resources", [])
                return success_response(
                    {"resources": resources, "total": len(resources)}
                )
        except Exception as e:
            logger.error(f"Error querying scan results: {str(e)}")

        return success_response({"resources": [], "total": 0})

    except Exception as e:
        logger.error(f"Error getting all resources: {str(e)}")
        return error_response("Failed to get all resources")


def success_response(data):
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token",
            "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
        },
        "body": json.dumps(data, default=str),
    }


def error_response(message, status_code=400):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token",
            "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
        },
        "body": json.dumps({"error": message}),
    }


def cors_response():
    return {
        "statusCode": 200,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token",
            "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
            "Access-Control-Max-Age": "86400",
        },
        "body": "",
    }
