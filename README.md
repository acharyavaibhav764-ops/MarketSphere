# MarketSphere

<p align="center">
  <img src="https://img.shields.io/badge/MarketSphere-Market%20Intelligence-10B981?style=for-the-badge&labelColor=0F172A" alt="MarketSphere" />
</p>

<p align="center">
  <strong>Real-time market intelligence, ranked and visualised.</strong><br/>
  Aggregate live economic data Â· Score & rank markets Â· Explore in a live dashboard
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.12" />
  <img src="https://img.shields.io/badge/FastAPI-0.111-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker&logoColor=white" alt="Docker" />
  <img src="https://img.shields.io/badge/JavaScript-ES2024-F7DF1E?style=flat-square&logo=javascript&logoColor=black" alt="JavaScript" />
  <img src="https://img.shields.io/badge/Data-Live%20Feeds-10B981?style=flat-square&logo=databricks&logoColor=white" alt="Live Data" />
  <img src="https://img.shields.io/badge/License-MIT-6366F1?style=flat-square" alt="MIT License" />
</p>

---

## ðŸš€ Overview

**MarketSphere** is a full-stack market intelligence platform that aggregates live economic and market data, runs it through a scoring and ranking pipeline, and presents the results in a real-time web dashboard.

Built with a **FastAPI** backend, a **JavaScript** frontend, and deployed via **Docker Compose**, MarketSphere gives analysts, researchers, and developers instant access to ranked, comparable market metrics across geographies â€” without manual data wrangling.

> Think of it as a Bloomberg terminal for open economic data â€” self-hosted, extensible, and free.

---

## âœ¨ Features

| Feature | Description |
|---|---|
| ðŸ“¡ **Live Data Feeds** | Pulls real-time data from World Bank, governance indices, and other open APIs |
| ðŸ§® **Ranking Engine** | Configurable scoring pipeline that ranks markets by composite indicators |
| ðŸŒ **Web Dashboard** | Interactive JS/HTML/CSS dashboard â€” no framework bloat, pure performance |
| âš¡ **FastAPI Backend** | Async REST API with automatic OpenAPI docs at `/docs` |
| ðŸ³ **Docker Compose** | One-command launch for the full stack â€” no dependency hell |
| ðŸ”Œ **Extensible Parsers** | Plug-in data parsers to add new sources in minutes |
| ðŸ“Š **Data Models** | Clean, typed Python models for every market entity |

---

## ðŸ—ï¸ Architecture

| Layer | Directory | Technology | Responsibility |
|---|---|---|---|
| **API** | `api/` | FastAPI (Python) | REST endpoints, request routing, OpenAPI docs |
| **Frontend** | `frontend/` | JavaScript / HTML / CSS | Interactive dashboard, charts, live updates |
| **Data Feeds** | `data_feeds/` | Python async clients | Live ingestion from World Bank, governance APIs |
| **Ranking Engine** | `ranking_engine/` | Python | Composite scoring & market ranking pipeline |
| **Parsers** | `parsers/` | Python | Raw response â†’ structured data transformation |
| **Services** | `services/` | Python | Business logic orchestration layer |
| **Models** | `models/` | Pydantic / Python | Typed data models shared across the stack |
| **Core** | `core/` | Python | Shared utilities, config, constants |
| **Infra** | `docker-compose.yml` | Docker Compose | Multi-service orchestration & networking |

---

## ðŸ”„ Data Pipeline

```
  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
  â”‚                    DATA SOURCES                     â”‚
  â”‚   World Bank API  Â·  Governance Indices  Â·  Custom  â”‚
  â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                          â”‚  HTTP / WebSocket
                          â–¼
              â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
              â”‚     data_feeds/       â”‚  â† Live async feed clients
              â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                          â”‚  raw JSON / CSV
                          â–¼
              â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
              â”‚      parsers/         â”‚  â† Normalise & validate
              â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                          â”‚  typed Python objects
                          â–¼
              â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
              â”‚     models/           â”‚  â† Pydantic schemas
              â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                          â”‚
                          â–¼
              â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
              â”‚   ranking_engine/     â”‚  â† Score & rank markets
              â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                          â”‚  ranked results
                          â–¼
              â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
              â”‚    services/  +  api/ â”‚  â† Orchestrate & expose
              â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                          â”‚  REST JSON
                          â–¼
              â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
              â”‚     frontend/         â”‚  â† Live web dashboard
              â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
```

---

## ðŸŒ Service URLs

| Service | URL | Description |
|---|---|---|
| **Dashboard** | `http://localhost:8080` | Live market intelligence dashboard |
| **API** | `http://localhost:8000` | FastAPI REST backend |
| **API Docs** | `http://localhost:8000/docs` | Interactive Swagger / OpenAPI UI |
| **API Redoc** | `http://localhost:8000/redoc` | ReDoc alternative API reference |

---

## ðŸ“¦ Installation

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (includes Docker Compose)
- [Git](https://git-scm.com/)

### Clone & Launch

```bash
# 1. Clone the repository
git clone https://github.com/acharyavaibhav764-ops/MarketSphere.git
cd MarketSphere

# 2. Launch the full stack
docker compose up --build
```

That's it. All services start automatically.

---

## â–¶ï¸ Usage

### One-Command Demo (Windows)

```bat
run-demo.bat
```

This builds and starts all containers, then opens the dashboard in your default browser.

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

# Get a specific market by ID
curl http://localhost:8000/api/markets/{market_id}

# Trigger a data refresh
curl -X POST http://localhost:8000/api/refresh
```

---

## âš™ï¸ Configuration

Environment variables can be set in a `.env` file at the project root (copy `.env.example` if present):

```env
# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
LOG_LEVEL=info

# Data Feeds
WORLD_BANK_API_BASE=https://api.worldbank.org/v2
FEED_REFRESH_INTERVAL_SECONDS=300

# Ranking Engine
RANKING_COMPOSITE_WEIGHTS=gdp:0.4,governance:0.3,stability:0.3
```

---

## ðŸ Local Development

For development without Docker:

```bash
# Create and activate a virtual environment
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the FastAPI dev server (with auto-reload)
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# In a separate terminal â€” serve the frontend
cd frontend
python -m http.server 8080
```

The API will hot-reload on file changes.

---

## ðŸ—‚ï¸ Project Structure

```
MarketSphere/
â”œâ”€â”€ api/                  # FastAPI application & route handlers
â”œâ”€â”€ frontend/             # HTML / CSS / JavaScript dashboard
â”œâ”€â”€ data_feeds/           # Async live data feed clients
â”œâ”€â”€ ranking_engine/       # Market scoring & ranking pipeline
â”œâ”€â”€ parsers/              # Raw data â†’ typed model parsers
â”œâ”€â”€ services/             # Business logic & orchestration
â”œâ”€â”€ models/               # Pydantic data models
â”œâ”€â”€ core/                 # Shared config, utils, constants
â”œâ”€â”€ docker-compose.yml    # Multi-service Docker orchestration
â”œâ”€â”€ Dockerfile            # Container build definition
â”œâ”€â”€ run-demo.bat          # One-command Windows demo launcher
â””â”€â”€ requirements.txt      # Python dependencies
```

---

## ðŸ“„ License

This project is licensed under the **MIT License** â€” see the [LICENSE](LICENSE) file for details.

---

<p align="center">
  Built with â¤ï¸ using <strong>FastAPI</strong>, <strong>Docker</strong>, and open economic data.<br/>
  <em>MarketSphere â€” because market intelligence should be open.</em>
</p>
