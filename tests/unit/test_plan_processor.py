"""
Unit tests for plan_processor Lambda function
"""

import json
import pytest
from unittest.mock import Mock, patch
import sys
import os

# Add backend/lambda to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend', 'lambda'))

# Mock boto3 before importing modules that use it
with patch('boto3.client'), patch('boto3.resource'):
    from plan_processor import process_terraform_plan, sanitize_db_input


class TestPlanProcessor:
    """Test cases for plan processor functionality"""

    def test_process_terraform_plan_no_changes(self):
        """Test processing plan with no changes"""
        plan_content = """
        No changes. Your infrastructure matches the configuration.

        Terraform has compared your real infrastructure against your configuration
        and found no differences, so no changes are needed.
        """

        result = process_terraform_plan(plan_content, "test-repo")

        assert result["drift_detected"] is False
        assert result["changes"] == []
        assert result["total_changes"] == 0
        assert result["status"] == "no_drift"

    def test_process_terraform_plan_with_changes(self):
        """Test processing plan with resource changes"""
        plan_content = """
        # aws_s3_bucket.example will be created
        + resource "aws_s3_bucket" "example" {
            + bucket = "my-bucket"
        }

        # aws_instance.web will be updated in-place
        ~ resource "aws_instance" "web" {
            instance_type = "t2.micro" -> "t2.small"
        }
        """

        result = process_terraform_plan(plan_content, "test-repo")

        assert result["drift_detected"] is True
        assert len(result["changes"]) == 2
        assert result["total_changes"] == 2
        assert result["status"] == "drift_detected"
        assert "Create: aws_s3_bucket.example" in result["changes"]
        assert "Update: aws_instance.web" in result["changes"]

    def test_sanitize_db_input(self):
        """Test database input sanitization"""
        # Test normal input
        assert sanitize_db_input("normal-repo_name.123") == "normal-repo_name.123"

        # Test input with dangerous characters
        assert sanitize_db_input("repo'; DROP TABLE--") == "repo_DROP_TABLE--"

        # Test long input truncation
        long_input = "a" * 2000
        result = sanitize_db_input(long_input)
        assert len(result) == 1000

    def test_process_terraform_plan_destroy_resources(self):
        """Test processing plan with resource destruction"""
        plan_content = """
        # aws_instance.old will be destroyed
        - resource "aws_instance" "old" {
            - ami = "ami-12345"
        }
        """

        result = process_terraform_plan(plan_content, "test-repo")

        assert result["drift_detected"] is True
        assert "Destroy: aws_instance.old" in result["changes"]

    def test_process_terraform_plan_replace_resources(self):
        """Test processing plan with resource replacement"""
        plan_content = """
        # aws_instance.web must be replaced
        -/+ resource "aws_instance" "web" {
            ~ ami = "ami-12345" -> "ami-67890"
        }
        """

        result = process_terraform_plan(plan_content, "test-repo")

        assert result["drift_detected"] is True
        assert "Replace: aws_instance.web" in result["changes"]
