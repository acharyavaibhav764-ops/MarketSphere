# MarketSphere

<p align="center">
  <img src="https://img.shields.io/badge/MarketSphere-Market%20Intelligence-10B981?style=for-the-badge&labelColor=0F172A" alt="MarketSphere" />
</p>

<p align="center">
  <strong>Real-time market intelligence, ranked and visualised.</strong><br/>
  Aggregate live economic data &middot; Score &amp; rank markets &middot; Explore in a live dashboard
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.12" />
  <img src="https://img.shields.io/badge/FastAPI-0.111-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker&logoColor=white" alt="Docker" />
  <img src="https://img.shields.io/badge/JavaScript-ES2024-F7DF1E?style=flat-square&logo=javascript&logoColor=black" alt="JavaScript" />
  <img src="https://img.shields.io/badge/Data-Live%20Feeds-10B981?style=flat-square" alt="Live Data" />
</p>

---

## Overview

**MarketSphere** is a full-stack market intelligence platform that aggregates live macroeconomic and governance data, runs it through a composite scoring and ranking pipeline, and surfaces the results in a real-time web dashboard.

Built with a **FastAPI** backend, a **JavaScript** frontend, and deployed via **Docker Compose** -- MarketSphere gives analysts, researchers, and developers instant access to ranked, comparable market metrics across geographies, without manual data wrangling.

---

## Features

| Feature | Description |
|---|---|
| **Live Data Feeds** | Pulls real-time data from World Bank, governance indices, and other open APIs |
| **Ranking Engine** | Configurable scoring pipeline that ranks markets by composite indicators |
| **Web Dashboard** | Interactive JS/HTML/CSS dashboard -- no framework bloat, pure performance |
| **FastAPI Backend** | Async REST API with automatic OpenAPI docs at `/docs` |
| **Docker Compose** | One-command launch for the full stack |
| **Extensible Parsers** | Plug-in data parsers to add new sources in minutes |
| **Typed Data Models** | Clean Pydantic models for every market entity |

---

## Architecture

| Layer | Directory | Technology | Responsibility |
|---|---|---|---|
| **API** | `api/` | FastAPI (Python) | REST endpoints, request routing, OpenAPI docs |
| **Frontend** | `frontend/` | JavaScript / HTML / CSS | Interactive dashboard, charts, live updates |
| **Data Feeds** | `data_feeds/` | Python async clients | Live ingestion from World Bank, governance APIs |
| **Ranking Engine** | `ranking_engine/` | Python | Composite scoring and market ranking pipeline |
| **Parsers** | `parsers/` | Python | Raw response to structured data transformation |
| **Services** | `services/` | Python | Business logic orchestration layer |
| **Models** | `models/` | Pydantic / Python | Typed data models shared across the stack |
| **Core** | `core/` | Python | Shared utilities, config, constants |
| **Infra** | `docker-compose.yml` | Docker Compose | Multi-service orchestration and networking |

---

## Data Pipeline

```
+-------------------------------------------------------+
|                     DATA SOURCES                      |
|   World Bank API  .  Governance Indices  .  Custom    |
+------------------------+------------------------------+
                         |  HTTP / WebSocket
                         v
              +-------------------------+
              |      data_feeds/        |  <- Live async feed clients
              +------------+------------+
                           |  raw JSON / CSV
                           v
              +-------------------------+
              |       parsers/          |  <- Normalise and validate
              +------------+------------+
                           |  typed Python objects
                           v
              +-------------------------+
              |        models/          |  <- Pydantic schemas
              +------------+------------+
                           |
                           v
              +-------------------------+
              |    ranking_engine/      |  <- Score and rank markets
              +------------+------------+
                           |  ranked results
                           v
              +-------------------------+
              |   services/  +  api/   |  <- Orchestrate and expose
              +------------+------------+
                           |  REST JSON
                           v
              +-------------------------+
              |       frontend/         |  <- Live web dashboard
              +-------------------------+
```

---

## Service URLs

| Service | URL | Description |
|---|---|---|
| **Dashboard** | `http://localhost:8080` | Live market intelligence dashboard |
| **API** | `http://localhost:8000` | FastAPI REST backend |
| **Swagger UI** | `http://localhost:8000/docs` | Interactive API documentation |
| **ReDoc** | `http://localhost:8000/redoc` | Alternative API reference |

---

## Installation

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (includes Docker Compose)
- [Git](https://git-scm.com/)

### Clone and Launch

```bash
git clone https://github.com/acharyavaibhav764-ops/MarketSphere.git
cd MarketSphere
docker compose up --build
```

---

## Usage

### One-Command Demo (Windows)

```bat
run-demo.bat
```

### Docker Compose

```bash
# Start all services
docker compose up

# Start in detached mode
docker compose up -d

# Stop all services
docker compose down

# Rebuild after code changes
docker compose up --build
```

### API Examples

```bash
# Get all ranked markets
curl http://localhost:8000/api/markets

# Trigger a data refresh
curl -X POST http://localhost:8000/api/refresh
```

---

## Configuration

Create a `.env` file at the project root:

```env
API_HOST=0.0.0.0
API_PORT=8000
LOG_LEVEL=info
WORLD_BANK_API_BASE=https://api.worldbank.org/v2
FEED_REFRESH_INTERVAL_SECONDS=300
RANKING_COMPOSITE_WEIGHTS=gdp:0.4,governance:0.3,stability:0.3
```

---

## Local Development

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # macOS / Linux

pip install -r requirements.txt
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

---

## Project Structure

```
MarketSphere/
|-- api/                  # FastAPI application and route handlers
|-- frontend/             # HTML / CSS / JavaScript dashboard
|-- data_feeds/           # Async live data feed clients
|-- ranking_engine/       # Market scoring and ranking pipeline
|-- parsers/              # Raw data to typed model parsers
|-- services/             # Business logic and orchestration
|-- models/               # Pydantic data models
|-- core/                 # Shared config, utils, constants
|-- docker-compose.yml    # Multi-service Docker orchestration
|-- Dockerfile            # Container build definition
|-- run-demo.bat          # One-command Windows demo launcher
`-- requirements.txt      # Python dependencies
```

---

<p align="center">
  Built with FastAPI, Docker, and open economic data.<br/>
  <em>MarketSphere -- because market intelligence should be open.</em>
</p>