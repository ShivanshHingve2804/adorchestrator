# 🚀 AdOrchestrator

> Fault-tolerant ad campaign orchestrator & creative analytics engine.

**Built to demonstrate production-grade backend engineering:** distributed workflows, concurrent-safe budget management, high-throughput analytics over 10M events, and AI-powered creative analysis.

## 🏗️ Architecture

<!-- TODO: Add architecture diagram after Phase 1 -->

## 🛠️ Tech Stack

| Layer | Technologies |
|---|---|
| **Core Backend** | Python 3.12, Django 5.1, Django REST Framework |
| **Durable Workflows** | Temporal (Python SDK) |
| **Async Tasks** | Celery, RabbitMQ |
| **Database** | PostgreSQL 16 (partitioned tables, materialized views) |
| **Cache & Locks** | Redis 7 (caching, distributed locks) |
| **AI / LLMs** | Gemini 2.0 Flash, Ollama (local), OpenAI (optional) |
| **Mock Platforms** | FastAPI (simulating Meta, TikTok, Google Ads APIs with chaos injection) |
| **Infrastructure** | Docker, Docker Compose, GitHub Actions CI/CD |

## 🚀 Quick Start

```bash
# Clone and start
git clone https://github.com/YOUR_USERNAME/adorchestrator.git
cd adorchestrator
cp .env.example .env

# Start all services (10 containers)
docker compose up -d

# Run migrations
make migrate

# Seed test data (10M ad events)
make seed

# Run tests
make test

# Run chaos tests (kill workers mid-flight → verify zero duplicates)
make chaos

# Load test (100 concurrent users)
make loadtest
```

## 📊 Key Engineering Decisions

### 1. Durable Workflows with Temporal
- Bulk campaign launches across 3 platforms with retry, exponential backoff, and saga compensation
- Zero duplicate launches even when workers crash mid-flight

### 2. Race-Safe Budget Management
- Redis distributed locks + PostgreSQL `SELECT FOR UPDATE`
- 20 concurrent budget writers → zero data corruption

### 3. Sub-200ms Analytics at 10M Events
- Table partitioning + materialized views + Redis caching

### 4. AI Creative Analysis
- VLM extracts visual features → correlates with ROAS/CTR
- Automated weekly summaries via LLM

## 🧪 Testing

```bash
make test       # Full test suite (180+ tests)
make chaos      # Chaos: kill workers, verify zero duplicates
make loadtest   # Locust: 100 concurrent users
```

## 📁 Project Structure

```
adorchestrator/
├── adorchestrator/          # Django project config
├── apps/
│   ├── campaigns/           # Campaign + Creative CRUD
│   ├── analytics/           # Reporting + Alerting
│   ├── creative_ai/         # AI Feature Extraction
│   └── budgets/             # Budget management + locking
├── workflows/               # Temporal workflows & activities
├── workers/                 # Celery tasks
├── mock_platforms/          # Fake Meta/TikTok/Google APIs
├── tests/                   # Load + chaos tests
├── scripts/                 # Data seeding
└── docs/                    # Architecture + benchmarks
```

## 📄 License

MIT
