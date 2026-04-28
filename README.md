# Nexus

Codebase knowledge graph service. Loads [graphify](https://github.com/noplannomercy/graphify) output into Apache AGE and exposes it via REST API and MCP SSE server.

## What it does

- Stores codebase graphs (nodes + edges + communities) in Apache AGE (PostgreSQL graph extension)
- **REST API** (FastAPI, port 8004) — query nodes, neighbors, communities, shortest paths, keyword search
- **MCP SSE server** (port 8006) — same queries as MCP tools, consumable by Claude and other AI agents
- **Rebuild endpoint** — triggers a fresh graph load from graphify output in the background

## Requirements

- Python 3.11+
- PostgreSQL 16 with [Apache AGE 1.6](https://age.apache.org/) extension

## Setup

```bash
git clone https://github.com/noplannomercy/nexus
cd nexus
pip install -r requirements.txt
cp .env.example .env
# edit .env — set AGE_DSN to your PostgreSQL connection string
```

## Configuration

| Variable | Default | Description |
|---|---|---|
| `AGE_DSN` | *required* | `postgresql://user:pass@host:port/db` |
| `AGE_GRAPH` | `codebase` | AGE graph name |
| `API_PORT` | `8004` | REST API port |
| `MCP_PORT` | `8006` | MCP SSE server port |
| `API_KEY` | *(empty)* | If set, requires `X-Api-Key` header |
| `GRAPHIFY_PATH` | `graphify` | Path to graphify binary |
| `SOURCE_DIR` | `.` | Source directory for graphify |
| `GRAPH_OUTPUT_PATH` | `graphify-out/graph.json` | graphify output path |

## Running

```bash
# REST API
python run_api.py

# MCP SSE server
python run_mcp.py
```

## REST API

Base URL: `http://localhost:8004`

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Health check |
| GET | `/graph/node/{id}` | Get node by ID |
| GET | `/graph/neighbors/{id}?depth=1` | Get neighbors within N hops |
| GET | `/graph/community/{id}` | Get all nodes in a community |
| GET | `/graph/god-nodes?limit=10` | Highest-degree nodes |
| GET | `/graph/stats` | Node and edge counts |
| GET | `/graph/path?src=A&dst=B` | Shortest path between two nodes |
| POST | `/graph/search` | Keyword search + neighbor expansion |
| POST | `/rebuild/` | Reload graph from graphify output |

### Keyword search request body

```json
{ "keywords": ["UserService", "auth"], "hops": 1 }
```

### API key auth

Set `API_KEY` in `.env`. All `/graph/*` and `/rebuild/*` endpoints require:

```
X-Api-Key: your-key
```

Leave `API_KEY` empty to disable auth.

## MCP

Nexus exposes the same 7 query functions as MCP tools over SSE transport.

Add to your `.mcp.json`:

```json
{
  "mcpServers": {
    "nexus": {
      "url": "http://localhost:8006/sse"
    }
  }
}
```

Available tools: `get_node`, `get_neighbors`, `get_community`, `god_nodes`, `graph_stats`, `shortest_path`, `keyword_search`

## Rebuild

`POST /rebuild/` starts a background thread that:
1. Sets a rebuild flag (all read endpoints return 503 during rebuild)
2. Runs graphify on `SOURCE_DIR`
3. Loads the output into AGE
4. Clears the flag

## Loading a graph manually

```bash
python -c "
from loader.age_loader import run_loader
run_loader(
    dsn='postgresql://user:pass@host:port/db',
    graph_name='codebase',
    graph_path='graphify-out/graph.json'
)
"
```

## Tests

```bash
pytest tests/ -v
```

Requires a live AGE DB (set `AGE_DSN` in `.env`). The test suite creates and tears down a `codebase_test` graph automatically.

## Architecture

```
core/age_queries.py     ThreadedConnectionPool + 7 query functions
api/main.py             FastAPI app, lifespan, auth middleware, rebuild guard
api/routes/graph.py     8 REST endpoints
api/routes/rebuild.py   Rebuild trigger endpoint
loader/age_loader.py    graph.json → AGE loader (ported from graphify_age_loader)
nexus_mcp/server.py     MCP SSE server (Starlette + mcp Python SDK)
```
