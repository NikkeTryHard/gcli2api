.PHONY: help install install-dev test lint format clean run docker-build docker-run docker-compose-up docker-compose-down test-cov test-thinking

help:
	@echo "gcli2api - Development Commands"
	@echo ""
	@echo "Available commands:"
	@echo "  make install            - Install production dependencies"
	@echo "  make install-dev        - Install development dependencies"
	@echo "  make test               - Run tests"
	@echo "  make test-cov           - Run tests with coverage report"
	@echo "  make test-thinking      - Run tests with 80% coverage for thinking-related code"
	@echo "  make lint               - Run linters (flake8, mypy)"
	@echo "  make format             - Format code with black"
	@echo "  make format-check       - Check code formatting without making changes"
	@echo "  make clean              - Clean build artifacts and cache"
	@echo "  make run                - Run the application"
	@echo "  make docker-build       - Build Docker image"
	@echo "  make docker-run         - Run Docker container"
	@echo "  make docker-compose-up  - Start services with docker-compose"
	@echo "  make docker-compose-down - Stop services with docker-compose"

install:
	pip install -r requirements.txt

install-dev:
	pip install -e ".[dev]"
	pip install -r requirements-dev.txt

test:
	python -m pytest tests/ -v

test-cov:
	python -m pytest tests/ --cov=src --cov-report=term-missing --cov-report=html

# Run tests with coverage for thinking-related files
# anthropic_streaming.py: 80%+ (core streaming conversion)
# antigravity_anthropic_router.py: 80%+ (API routes with integration tests)
test-thinking:
	@echo "Running tests with coverage for thinking-related files..."
	@echo "=============================================="
	@echo "Checking anthropic_streaming.py (80% required)"
	@echo "=============================================="
	python -m pytest tests/ \
		--cov=src.anthropic_streaming \
		--cov-report=term-missing \
		--cov-fail-under=80 -q
	@echo ""
	@echo "=============================================="
	@echo "Checking antigravity_anthropic_router.py (80% required)"
	@echo "=============================================="
	python -m pytest tests/ \
		--cov=src.antigravity_anthropic_router \
		--cov-report=term-missing \
		--cov-fail-under=80 -q
	@echo ""
	@echo "Thinking-related code coverage: PASSED"

lint:
	python -m flake8 src/ web.py config.py log.py --max-line-length=100 --extend-ignore=E203,W503
	python -m mypy src/ --ignore-missing-imports

format:
	python -m black src/ web.py config.py log.py test_*.py

format-check:
	python -m black --check src/ web.py config.py log.py test_*.py

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.log" -delete
	rm -rf .pytest_cache .mypy_cache .coverage htmlcov/ build/ dist/ *.egg-info

run:
	python web.py

docker-build:
	docker build -t gcli2api:latest .

docker-run:
	docker run -d --name gcli2api --network host -e PASSWORD=pwd -e PORT=7861 -v $$(pwd)/data/creds:/app/creds gcli2api:latest

docker-compose-up:
	docker-compose up -d

docker-compose-down:
	docker-compose down
