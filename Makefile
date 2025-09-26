# CloudOps Assistant Makefile - Single Stack Architecture

# Load environment variables from backend/.env file
include backend/.env
export

STACK_NAME := $(or $(STACK_NAME),cloudops-assistant)
AWS_REGION := $(or $(AWS_REGION),us-east-1)

###
# AWS Deployment
###

# Default target - deploy stack
deploy:
	sam build
	sam deploy --stack-name $(STACK_NAME) --resolve-s3 --resolve-image-repos --capabilities CAPABILITY_IAM --region $(AWS_REGION)
	$(MAKE) update-config

# Deploy with guided setup
deploy-guided:
	sam build
	sam deploy --guided --stack-name $(STACK_NAME) --capabilities CAPABILITY_IAM --region $(AWS_REGION)
	$(MAKE) update-config

# Teardown stack
teardown:
	aws cloudformation delete-stack --stack-name $(STACK_NAME)

# Get stack outputs
outputs:
	aws cloudformation describe-stacks --stack-name $(STACK_NAME) --query "Stacks[0].Outputs" --output table

# Generate frontend configuration from stack output
update-config:
	python scripts/generate_frontend_config.py --stack-name $(STACK_NAME) --environment $(ENVIRONMENT)
	cd frontend && node build-config.js

# Test API endpoints after deployment
test-api:
	python scripts/test_api.py $(STACK_NAME)

# View logs
logs:
	sam logs --stack-name $(STACK_NAME) --tail

# Serve frontend locally (generates config first)
serve-frontend: update-config
	cd frontend && python -m http.server 3000

# Add custom configuration to frontend config
add-config:
	@echo "Usage: make add-config CONFIG='CUSTOM_KEY: \"value\",'"
	@if [ -z "$(CONFIG)" ]; then echo "Error: CONFIG parameter required"; exit 1; fi
	python scripts/add_custom_config.py "$(CONFIG)"

###
# Setup
###

# Install all dependencies
install:
	pip install -r requirements.txt
	pip install -r requirements-dev.txt

###
# Local Development
###

# Serve frontend for local development (no stack required)
serve-local:
	cp frontend/config.local.js frontend/config.js
	cd frontend && python -m http.server 3000

# Local development with LocalStack
dev-start:
	cd local && docker compose up -d
	@echo "Waiting for LocalStack to start..."
	powershell -Command "Start-Sleep -Seconds 15"
	cd local && pip install -r requirements.txt
	@echo "Deploying SAM template to LocalStack..."
	cd local && python deploy-to-localstack.py
	cd local && python local_server.py

# Local development with AI (Ollama)
dev-start-ai:
	cd local && docker compose up -d
	@echo "Waiting for services to start..."
	powershell -Command "Start-Sleep -Seconds 20"
	cd local && pip install -r requirements.txt
	@echo "Setting up Ollama AI model..."
	cd local && python setup_local_ai.py
	@echo "Deploying SAM template to LocalStack..."
	cd local && python deploy-to-localstack.py
	cd local && python local_server.py

# Setup AI model only
dev-setup-ai:
	cd local && python setup_local_ai.py

# Stop local development
dev-stop:
	cd local && docker compose down

# View local development logs
dev-logs:
	cd local && docker compose logs -f

# Clean local development environment
dev-clean:
	cd local && docker compose down -v
	cd local && docker system prune -f

###
# Testing & Quality
###

# Format and lint code
check:
	python -m black backend/lambda/
	python -m isort backend/lambda/
	python -m flake8 backend/lambda/
	-python -m pylint backend/lambda/

# Security scan
security:
	-python -m bandit -r backend/lambda/
	-python -m safety check

# Run all tests (unit tests only, integration tests require deployed API)
test:
	python -m pytest tests/unit/ --cov=backend/lambda/

# Run only unit tests
test-unit:
	python -m pytest tests/unit/ --cov=backend/lambda/ -v

# Run only integration tests
test-integration:
	python -m pytest tests/integration/ -v

# Run authentication tests specifically
test-auth:
	python -m pytest tests/integration/test_user_authentication.py -v

# Run tests with detailed coverage report
test-coverage:
	python -m pytest tests/ --cov=backend/lambda/ --cov-report=html --cov-report=term-missing

# Run specific test file
test-file:
	@echo "Usage: make test-file FILE=test_plan_processor.py"
	@if [ -z "$(FILE)" ]; then echo "Error: FILE parameter required"; exit 1; fi
	python -m pytest tests/unit/$(FILE) -v

# Validate project rules compliance
validate-rules:
	@echo "Project rules validation not yet implemented"

# Validate configuration synchronization
validate-config:
	python scripts/validate_config.py

# Quality checks (format + lint + security + test)
quality: check security test validate-rules
	-python scripts/validate_config.py

# Test local development endpoints (simple connectivity)
dev-test:
	cd local && python simple_endpoint_test.py

# Test AI integration
dev-test-ai:
	cd local && python test_ai_integration.py

# Run all local tests
dev-test-all: dev-test dev-test-ai

# Full comprehensive check (quality + integration tests)
full-check: quality dev-test-all

###
# Utilities
###

# Clean build artifacts
clean:
	rmdir /s /q .aws-sam

# Validate template
validate:
	sam validate

# Clean EOL data for fresh scan
cleanup-eol:
	python scripts/cleanup_eol_data.py

# Build and deploy terraform executor container
build-terraform-executor:
	cd backend/terraform-executor && build-and-deploy.bat

# Deploy with terraform executor
deploy-with-terraform:
	$(MAKE) build-terraform-executor
	$(MAKE) deploy

.PHONY: deploy deploy-guided teardown outputs update-config test-api logs serve-frontend install serve-local dev-start dev-start-ai dev-setup-ai dev-stop dev-logs dev-clean check security test dev-test dev-test-ai dev-test-all quality full-check validate-rules validate-config clean validate cleanup-eol build-terraform-executor deploy-with-terraform
