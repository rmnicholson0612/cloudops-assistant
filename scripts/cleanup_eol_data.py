#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Clean EOL DynamoDB tables for fresh scan
"""
import boto3
import sys
import os
from botocore.exceptions import ClientError

def cleanup_eol_tables():
    """Clean all EOL-related DynamoDB tables"""
    try:
        # Check if using LocalStack
        endpoint_url = None
        if (os.environ.get('AWS_ENDPOINT_URL') and 'localhost:4566' in os.environ.get('AWS_ENDPOINT_URL')) or os.path.exists('local/docker-compose.yml'):
            endpoint_url = 'http://localhost:4566'
            print("[INFO] Using LocalStack endpoint")

        dynamodb = boto3.resource('dynamodb', endpoint_url=endpoint_url, region_name='us-east-1')

        # Table names from template.yaml
        tables_to_clean = [
            'cloudops-assistant-eol-scans',
            'cloudops-assistant-eol-database'
        ]

        total_deleted = 0

        for table_name in tables_to_clean:
            try:
                table = dynamodb.Table(table_name)

                # Scan and delete all items
                response = table.scan()
                items = response.get('Items', [])

                print(f"Found {len(items)} items in {table_name}")

                # Delete items in batches
                with table.batch_writer() as batch:
                    for item in items:
                        # Get the primary key for deletion
                        if table_name == 'cloudops-assistant-eol-scans':
                            batch.delete_item(Key={'scan_id': item['scan_id']})
                        elif table_name == 'cloudops-assistant-eol-database':
                            batch.delete_item(Key={'eol_id': item['eol_id']})
                        total_deleted += 1

                print(f"[OK] Cleaned {len(items)} items from {table_name}")

            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceNotFoundException':
                    print(f"[WARN] Table {table_name} not found - skipping")
                else:
                    print(f"[ERROR] Error cleaning {table_name}: {e}")
            except Exception as e:
                print(f"[ERROR] Error cleaning {table_name}: {e}")

        print(f"\n[SUCCESS] Cleanup complete! Deleted {total_deleted} total items")
        return True

    except Exception as e:
        print(f"[ERROR] Cleanup failed: {e}")
        return False

if __name__ == "__main__":
    print("[INFO] Cleaning EOL DynamoDB tables...")
    success = cleanup_eol_tables()
    sys.exit(0 if success else 1)
