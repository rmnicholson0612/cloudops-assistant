# Use Python base image for Fargate (not Lambda)
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install Terraform
RUN curl -fsSL -k https://releases.hashicorp.com/terraform/1.5.0/terraform_1.5.0_linux_amd64.zip -o terraform.zip \
    && unzip terraform.zip \
    && mv terraform /usr/local/bin/ \
    && rm terraform.zip

# Install Python dependencies
RUN pip install boto3

# Copy Fargate entrypoint
COPY fargate-entrypoint.py /usr/local/bin/fargate-entrypoint.py
RUN chmod +x /usr/local/bin/fargate-entrypoint.py

# Set working directory
WORKDIR /app

# Run the entrypoint script
CMD ["python3", "/usr/local/bin/fargate-entrypoint.py"]