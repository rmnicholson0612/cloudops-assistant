FROM public.ecr.aws/lambda/python:3.11

# Install terraform
RUN yum update -y && \
    yum install -y wget unzip && \
    wget https://releases.hashicorp.com/terraform/1.6.6/terraform_1.6.6_linux_amd64.zip && \
    unzip terraform_1.6.6_linux_amd64.zip && \
    mv terraform /usr/local/bin/ && \
    chmod +x /usr/local/bin/terraform && \
    rm terraform_1.6.6_linux_amd64.zip && \
    yum clean all

# Install git for repository cloning
RUN yum install -y git

# Copy requirements and install Python dependencies
COPY requirements.txt ${LAMBDA_TASK_ROOT}
RUN pip install -r requirements.txt

# Copy function code
COPY terraform_executor.py ${LAMBDA_TASK_ROOT}
COPY auth_utils.py ${LAMBDA_TASK_ROOT}

CMD ["terraform_executor.lambda_handler"]
