"""
Terraform plan fixtures for testing
"""

# No changes plan
NO_CHANGES_PLAN = """
No changes. Your infrastructure matches the configuration.

Terraform has compared your real infrastructure against your configuration
and found no differences, so no changes are needed.
"""

# Plan with creates, updates, destroys
MIXED_CHANGES_PLAN = """
# aws_s3_bucket.new will be created
+ resource "aws_s3_bucket" "new" {
    + bucket = "my-new-bucket"
  }

# aws_instance.web will be updated in-place
~ resource "aws_instance" "web" {
    ~ instance_type = "t2.micro" -> "t2.small"
  }

# aws_instance.old will be destroyed
- resource "aws_instance" "old" {
    - ami = "ami-12345"
  }

Plan: 1 to add, 1 to change, 1 to destroy.
"""

# Plan with ANSI color codes
COLORED_PLAN = """
\x1b[0m\x1b[1m# aws_s3_bucket.example will be created\x1b[0m\x1b[0m
\x1b[0m  \x1b[32m+\x1b[0m\x1b[0m resource "aws_s3_bucket" "example" {
      \x1b[32m+\x1b[0m\x1b[0m bucket = "test-bucket"
    }

\x1b[0m\x1b[1mPlan:\x1b[0m 1 to add, 0 to change, 0 to destroy.
"""

# Error plan
ERROR_PLAN = """
Error: Invalid configuration

The configuration is not valid:
- Missing required argument
"""
