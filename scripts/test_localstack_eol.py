#!/usr/bin/env python3
"""
Test LocalStack EOL table access and create sample data
"""
import boto3
import json
from datetime import datetime, timezone

def test_localstack_eol():
    """Test LocalStack EOL tables"""
    try:
        # Connect to LocalStack
        dynamodb = boto3.resource('dynamodb',
                                endpoint_url='http://localhost:4566',
                                region_name='us-east-1')

        # List all tables
        client = boto3.client('dynamodb',
                            endpoint_url='http://localhost:4566',
                            region_name='us-east-1')

        tables = client.list_tables()
        print(f"Available tables: {tables['TableNames']}")

        # Check if EOL tables exist
        eol_tables = [t for t in tables['TableNames'] if 'eol' in t.lower()]
        print(f"EOL tables found: {eol_tables}")

        if not eol_tables:
            print("No EOL tables found. You may need to deploy to LocalStack first.")
            return False

        # Test access to EOL scans table
        for table_name in eol_tables:
            table = dynamodb.Table(table_name)
            response = table.scan(Limit=5)
            items = response.get('Items', [])
            print(f"Table {table_name}: {len(items)} items")

            # Show sample items
            for item in items[:2]:
                print(f"  Sample item: {json.dumps(item, default=str, indent=2)[:200]}...")

        return True

    except Exception as e:
        print(f"Error testing LocalStack: {e}")
        return False

if __name__ == "__main__":
    test_localstack_eol()
