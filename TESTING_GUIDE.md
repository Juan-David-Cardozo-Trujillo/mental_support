# Testing & CI/CD Pipeline Guide

## Overview

The Mental Health Platform includes comprehensive testing and CI/CD infrastructure using GitHub Actions. The pipeline ensures code quality, security, and reliability before deployment.

---

## GitHub Actions Workflow

**File**: `.github/workflows/ci-cd.yml`

### Workflow Jobs

#### 1. **Lint & Format Check**

- **Python**: Flake8, Black, isort
- **JavaScript**: ESLint
- **Runs on**: Every push and PR

**Commands**:

```bash
# Local testing
flake8 backend/
black --check backend/
isort --check-only backend/
cd frontend && npm run lint
```

#### 2. **Backend Unit & Integration Tests**

- **Framework**: pytest with asyncio support
- **Coverage**: Target 80%+
- **Services**: PostgreSQL (test_auth, test_platform), Redis

**Configuration**:

```bash
# File: backend/tests/conftest.py
# Provides fixtures for database, sessions, mock users
```

**Run locally**:

```bash
pytest backend/tests/ --cov=backend --cov-report=html
```

#### 3. **Frontend Unit & Integration Tests**

- **Framework**: Jest/Vitest with React Testing Library
- **Coverage**: Target 60%+

**Configuration**:

```bash
# File: frontend/jest.config.json
# Provides Jest setup and module mapping
```

**Run locally**:

```bash
cd frontend && npm run test:coverage
```

#### 4. **Security Scanning**

- **Backend**: Bandit (Python security), Safety (dependencies)
- **Frontend**: npm audit

**Run locally**:

```bash
bandit -r backend/
safety check
npm audit
```

#### 5. **Docker Build**

- Builds backend and frontend images
- Pushes to GitHub Container Registry
- Only on main branch after tests pass

---

## Local Development

### Prerequisites

```bash
# Backend
pip install -r requirements.txt
pip install pytest pytest-asyncio pytest-cov pytest-mock

# Frontend
cd frontend
npm install
```

### Running Tests Locally

#### Backend Tests

```bash
# All tests
pytest backend/tests/ -v

# With coverage report
pytest backend/tests/ --cov=backend --cov-report=html

# Specific test file
pytest backend/tests/test_auth.py -v

# Specific test function
pytest backend/tests/test_auth.py::test_sso_start -v

# Watch mode (requires pytest-watch)
ptw backend/tests/

# Unit tests only
pytest backend/tests/ -m "not integration" -v

# Integration tests only
pytest backend/tests/ -m integration -v
```

#### Frontend Tests

```bash
# All tests
cd frontend && npm run test

# With coverage
npm run test:coverage

# Watch mode
npm run test:watch

# Specific test file
npm run test -- Landing.test.jsx

# Update snapshots
npm run test -- -u
```

#### Linting

```bash
# Backend
flake8 backend/ --count --statistics
black backend/ --check
isort backend/ --check-only

# Frontend
npm run lint

# Fix formatting
black backend/ --line-length=100
isort backend/
npm run lint -- --fix
```

---

## Test Structure

### Backend Tests

**Directory**: `backend/tests/`

```
backend/tests/
├── __init__.py
├── conftest.py              # Pytest fixtures
├── test_auth.py             # Auth router tests
├── test_assessment.py       # Assessment tests
├── test_matching.py         # Matching engine tests
├── test_chat.py             # Chat/WebSocket tests
├── test_appointments.py     # Appointment tests
├── test_resources.py        # Resource tests
├── test_peer.py             # Peer portal tests
├── test_professional.py     # Professional portal tests
└── integration/
    ├── test_auth_flow.py
    ├── test_chat_flow.py
    └── test_appointment_flow.py
```

**Fixture Examples**:

```python
# conftest.py provides:
@pytest.fixture
async def client(app):
    """HTTP client for testing"""

@pytest.fixture
def mock_user():
    """Mock student user"""

@pytest.fixture
def auth_session:
    """Test auth database session"""

@pytest.fixture
def platform_session:
    """Test platform database session"""
```

### Frontend Tests

**Directory**: `frontend/src/test/`

```
frontend/src/
├── test/
│   ├── setup.js             # Jest configuration
│   ├── Landing.test.jsx     # Example test
│   └── __mocks__/
│       └── fileMock.js
└── pages/
    ├── __tests__/
    │   ├── Landing.test.jsx
    │   ├── Dashboard.test.jsx
    │   ├── Dashboard.test.jsx
    │   └── ...
```

**Test Examples**:

```javascript
// Landing.test.jsx
describe("Landing Page", () => {
  test("renders SSO button", () => {
    render(<Landing />);
    expect(
      screen.getByRole("button", {
        name: /Login with University SSO/i,
      }),
    ).toBeInTheDocument();
  });
});
```

---

## Writing New Tests

### Backend Test Template

```python
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_endpoint_success(client: AsyncClient):
    """Test successful endpoint call."""
    response = await client.get("/api/v1/endpoint")

    assert response.status_code == 200
    data = response.json()
    assert "expected_field" in data
```

### Frontend Test Template

```javascript
import { render, screen, userEvent } from "../test/setup";
import Component from "../Component";

describe("Component Name", () => {
  test("renders correctly", () => {
    render(<Component />);
    expect(screen.getByText(/Expected Text/i)).toBeInTheDocument();
  });

  test("handles user interaction", async () => {
    const user = userEvent.setup();
    render(<Component />);

    await user.click(screen.getByRole("button"));
    expect(screen.getByText(/Success/i)).toBeInTheDocument();
  });
});
```

---

## Coverage Goals

### Backend

- **Target**: 80%+ coverage
- **Critical paths**: Auth, chat, burnout detection
- **Exclusions**: Migrations, **pycache**

### Frontend

- **Target**: 60%+ coverage
- **Critical paths**: Protected routes, auth flow, dashboards
- **Exclusions**: Placeholder pages, third-party libraries

### Command to check coverage

```bash
# Backend
pytest backend/tests/ --cov=backend --cov-report=term-missing

# Frontend
npm run test:coverage
```

---

## Continuous Integration Flow

```
┌──────────────────┐
│  Push to GitHub  │
└────────┬─────────┘
         │
         ▼
    ┌─────────────────┐
    │ Lint & Format   │
    └────────┬────────┘
             │
    ┌────────▼─────────────────────────┐
    │                                  │
    ▼                                  ▼
┌──────────────────┐         ┌──────────────────┐
│ Backend Tests    │         │ Frontend Tests   │
│ (pytest)         │         │ (Jest)           │
└────────┬─────────┘         └────────┬─────────┘
         │                           │
         └────────────┬──────────────┘
                      │
    ┌─────────────────▼──────────────────┐
    │                                    │
    ▼                                    ▼
┌──────────────────┐         ┌──────────────────┐
│ Security Scan    │         │ Security Scan    │
│ Backend (Bandit) │         │ Frontend (npm)   │
└────────┬─────────┘         └────────┬─────────┘
         │                           │
         └────────────┬──────────────┘
                      │
         ┌────────────▼──────────────┐
         │                          │
         ▼ (Success on main)         ▼ (Failure)
    ┌──────────────┐            ┌─────────┐
    │ Build Docker │            │ Notify  │
    │ & Push       │            │ Slack   │
    └──────────────┘            └─────────┘
```

---

## Deployment Readiness

### Pre-deployment Checklist

- [ ] All tests passing (80%+ backend, 60%+ frontend)
- [ ] No linting errors
- [ ] Security scans passed
- [ ] Docker images built successfully
- [ ] README and docs updated
- [ ] .env example includes new vars
- [ ] Database migrations ready

### Deploying to Production

```bash
# Verify tests pass locally
pytest backend/tests/ --cov=backend
npm run test:coverage

# Create release branch
git checkout -b release/v1.0.0

# Update version numbers
# Commit and push

# GitHub Actions will:
# 1. Run full CI/CD pipeline
# 2. Build Docker images
# 3. Push to registry
# 4. Create deployment artifacts
```

---

## Troubleshooting

### Tests Failing Locally

**Database connection refused**:

```bash
# Start PostgreSQL and Redis
docker-compose up -d auth_db platform_db redis

# Run tests
pytest backend/tests/
```

**Import errors**:

```bash
# Install dependencies
pip install -e .

# Or for frontend
npm install
```

**Async test errors**:

```bash
# Ensure pytest-asyncio is installed
pip install pytest-asyncio

# And configured in conftest.py
```

### GitHub Actions Failing

**Check logs**:

1. Go to Actions tab in GitHub
2. Click failed workflow
3. Expand "Run tests" step to see error
4. Fix locally and push again

**Common issues**:

- Database migration not run
- Missing environment variable
- Dependency version mismatch
- Port already in use

---

## Best Practices

1. **Write tests for critical paths**
   - Authentication
   - Burnout detection
   - Chat encryption
   - Appointment booking

2. **Use descriptive test names**

   ```python
   # Good
   def test_burnout_indicator_shows_red_when_sessions_exceed_20():

   # Bad
   def test_burnout():
   ```

3. **Mock external services**
   - SSO provider
   - Email service
   - Third-party APIs

4. **Keep tests independent**
   - No shared state
   - Use fixtures for setup/teardown
   - Each test should run in any order

5. **Test both success and failure paths**

   ```python
   # Success
   def test_login_success():

   # Failure
   def test_login_invalid_credentials():
   def test_login_user_not_found():
   ```

---

## Performance Testing

For load testing (optional):

```bash
# Using Apache Bench
ab -n 1000 -c 10 http://localhost:8000/health

# Using wrk (install separately)
wrk -t4 -c100 -d30s http://localhost:8000/health
```

---

## Monitoring & Alerts

In production, monitor:

- Test coverage trends
- Build success rate
- Deployment frequency
- Security scan results
- Performance metrics

---

**Status**: ✅ CI/CD Pipeline Complete  
**Coverage Target**: Backend 80%, Frontend 60%  
**Deployment Ready**: Yes, once tests passing
