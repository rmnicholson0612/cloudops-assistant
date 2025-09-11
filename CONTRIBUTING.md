# Contributing to CloudOps Assistant

Thank you for your interest in contributing to CloudOps Assistant! This document provides guidelines and information for contributors.

## 🚀 Quick Start

1. **Fork the repository**
2. **Clone your fork**
   ```bash
   git clone https://github.com/YOUR_USERNAME/cloudops-assistant.git
   cd cloudops-assistant
   ```
3. **Install development dependencies**
   ```bash
   pip install -r requirements-dev.txt
   ```
4. **Set up pre-commit hooks**
   ```bash
   pre-commit install
   ```

## 🛠️ Development Setup

### Prerequisites
- Python 3.11+
- AWS CLI configured
- SAM CLI installed
- Git

### Local Development
```bash
# Install dependencies
pip install -r requirements-dev.txt

# Run tests
pytest tests/

# Format code
black backend/lambda/
isort backend/lambda/

# Lint code
flake8 backend/lambda/
pylint backend/lambda/

# Validate SAM template
sam validate
```

## 📝 Code Style

We use automated code formatting and linting:

- **Black** for code formatting
- **isort** for import sorting
- **flake8** for linting
- **pylint** for additional code quality checks

Run `pre-commit run --all-files` to check your code before committing.

## 🧪 Testing

- Write unit tests for all new functionality
- Maintain test coverage above 80%
- Use pytest for testing
- Mock external dependencies (AWS services, HTTP calls)

```bash
# Run tests with coverage
pytest tests/ --cov=backend/lambda/ --cov-report=html
```

## 📋 Pull Request Process

1. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes**
   - Follow the code style guidelines
   - Add tests for new functionality
   - Update documentation as needed

3. **Run quality checks**
   ```bash
   pre-commit run --all-files
   pytest tests/
   ```

4. **Update documentation**
   - Update README.md if adding new features
   - Add architecture diagrams for significant changes
   - Update API documentation

5. **Submit pull request**
   - Use the PR template
   - Link to related issues
   - Provide clear description of changes

## 🏗️ Architecture Guidelines

- Follow serverless-first principles
- Use AWS SAM for infrastructure as code
- Implement proper error handling and logging
- Follow security best practices
- Design for cost optimization

## 📚 Documentation

- Keep README.md up to date
- Document all public APIs
- Include architecture diagrams for major changes
- Write clear commit messages
- Add inline comments for complex logic

## 🔒 Security

- Never commit secrets or credentials
- Use environment variables for configuration
- Follow AWS security best practices
- Run security scans before submitting PRs

## 🐛 Bug Reports

Use the bug report template and include:
- Clear description of the issue
- Steps to reproduce
- Expected vs actual behavior
- Environment details
- Relevant logs

## 💡 Feature Requests

Use the feature request template and include:
- Problem description
- Proposed solution
- Implementation considerations
- Acceptance criteria

## 📞 Getting Help

- Check existing issues and documentation
- Use the question issue template
- Join discussions in existing issues
- Be respectful and constructive

## 📄 License

By contributing, you agree that your contributions will be licensed under the MIT License.

## 🙏 Recognition

Contributors will be recognized in:
- README.md contributors section
- Release notes
- Project documentation

Thank you for helping make CloudOps Assistant better! 🚀
