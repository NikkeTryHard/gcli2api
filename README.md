# gcli2api

**GeminiCLI and Antigravity to OpenAI/Gemini/Anthropic API Proxy**

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: CNC-1.0](https://img.shields.io/badge/License-CNC--1.0-red.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/docker-available-blue.svg)](https://github.com/su-kaka/gcli2api/pkgs/container/gcli2api)
[![Deploy on Zeabur](https://zeabur.com/button.svg)](https://zeabur.com/templates/97VMEF?referralCode=su-kaka)

[English](docs/README_EN.md) | 中文

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Features](#features)
- [Installation](#installation)
- [Configuration](#configuration)
- [API Reference](#api-reference)
- [Claude Code Integration (antigravity2claudecode)](#claude-code-integration-antigravity2claudecode)
- [Storage Backends](#storage-backends)
- [Environment Variables](#environment-variables)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## Overview

gcli2api is a Python-based API proxy server that converts GeminiCLI and Google Antigravity API requests into OpenAI, Gemini, and Anthropic API-compatible formats. It enables seamless integration with various LLM clients by providing a unified API interface.

### Key Capabilities

- **Multi-format API support**: OpenAI, Gemini native, and Anthropic Messages API
- **Claude Code CLI integration**: Direct connection via Anthropic Messages API
- **Extended Thinking support**: Full thinking blocks, signatures, and budget control
- **Credential management**: OAuth rotation, health monitoring, and auto-recovery
- **Dual storage backends**: SQLite (default) and MongoDB for distributed deployments
- **Web management console**: OAuth flows, credential management, real-time logs

---

## Architecture

### System Overview

```mermaid
flowchart TB
    subgraph Clients["API Clients"]
        OAI[OpenAI Clients]
        GEM[Gemini Clients]
        CC[Claude Code CLI]
        CURL[cURL / HTTP]
    end

    subgraph Server["gcli2api Server :7861"]
        direction TB
        subgraph Routers["API Routers"]
            OR[openai_router.py]
            GR[gemini_router.py]
            AGR[antigravity_router.py]
            AAR[antigravity_anthropic_router.py]
        end

        subgraph Core["Core Modules"]
            FD[format_detector.py]
            OT[openai_transfer.py]
            AC[anthropic_converter.py]
            AS[anthropic_streaming.py]
            AT[anti_truncation.py]
        end

        subgraph Infra["Infrastructure"]
            CM[credential_manager.py]
            SM[state_manager.py]
            TM[task_manager.py]
            SA[storage_adapter.py]
        end

        subgraph Storage["Storage Layer"]
            SQL[(SQLite)]
            MDB[(MongoDB)]
        end
    end

    subgraph External["External APIs"]
        GCLI[GeminiCLI API]
        AGAPI[Antigravity API]
    end

    OAI --> OR
    GEM --> GR
    CC --> AAR
    CURL --> OR & GR & AGR & AAR

    OR --> FD --> OT
    GR --> OT
    AGR --> OT
    AAR --> AC --> AS

    OT --> CM
    AS --> CM
    CM --> GCLI & AGAPI
    CM --> SA
    SA --> SQL & MDB
```

### Request Flow - Claude Code Integration

```mermaid
sequenceDiagram
    participant CC as Claude Code CLI
    participant AAR as antigravity_anthropic_router
    participant AC as anthropic_converter
    participant API as antigravity_api
    participant CM as credential_manager
    participant AS as anthropic_streaming
    participant AG as Antigravity API

    CC->>AAR: POST /v1/messages (Anthropic format)
    AAR->>AAR: Validate x-api-key / Authorization
    AAR->>AC: Convert request format
    AC->>AC: Extract thinking params
    AC->>AC: Transform messages to Gemini format
    AC->>API: Send Gemini-format request
    API->>CM: Get active credential
    CM->>CM: OAuth token refresh if needed
    API->>AG: Forward request with OAuth
    AG-->>AS: SSE stream (Gemini format)

    loop For each SSE chunk
        AS->>AS: Parse Gemini SSE
        AS->>AS: Convert to Anthropic format
        AS->>AS: Handle thinking blocks
        AS-->>CC: Anthropic SSE event
    end

    AS-->>CC: message_stop event
```

### Module Architecture

```mermaid
flowchart LR
    subgraph API["API Layer"]
        direction TB
        A1[openai_router.py]
        A2[gemini_router.py]
        A3[antigravity_router.py]
        A4[antigravity_anthropic_router.py]
    end

    subgraph Transform["Transformation Layer"]
        direction TB
        T1[format_detector.py]
        T2[openai_transfer.py]
        T3[anthropic_converter.py]
        T4[anthropic_streaming.py]
        T5[anthropic_helpers.py]
    end

    subgraph Infra["Infrastructure Layer"]
        direction TB
        I1[credential_manager.py]
        I2[state_manager.py]
        I3[task_manager.py]
        I4[token_estimator.py]
        I5[anti_truncation.py]
    end

    subgraph Storage["Storage Layer"]
        direction TB
        S1[storage_adapter.py]
        S2[sqlite_manager.py]
        S3[mongodb_manager.py]
    end

    subgraph Web["Web Console"]
        direction TB
        W1[web_routes.py]
        W2[auth.py]
    end

    API --> Transform
    Transform --> Infra
    Infra --> Storage
    Web --> Infra
    Web --> Storage
```

---

## Features

### API Endpoints and Format Support

| Endpoint Type          | Path                                             | Format          | Description             |
| ---------------------- | ------------------------------------------------ | --------------- | ----------------------- |
| **OpenAI Compatible**  | `/v1/chat/completions`                           | OpenAI / Gemini | Auto-detect and convert |
| **OpenAI Compatible**  | `/v1/models`                                     | OpenAI          | List available models   |
| **Gemini Native**      | `/v1/models/{model}:generateContent`             | Gemini          | Non-streaming           |
| **Gemini Native**      | `/v1/models/{model}:streamGenerateContent`       | Gemini          | Streaming               |
| **Antigravity OpenAI** | `/antigravity/v1/chat/completions`               | OpenAI          | Antigravity backend     |
| **Antigravity Gemini** | `/antigravity/v1/models/{model}:generateContent` | Gemini          | Antigravity backend     |
| **Anthropic Messages** | `/v1/messages`                                   | Anthropic       | Claude Code compatible  |
| **Anthropic Messages** | `/v1/messages/count_tokens`                      | Anthropic       | Token counting          |

### Supported Models

#### GeminiCLI Models

| Model                        | Context Window | Features                |
| ---------------------------- | -------------- | ----------------------- |
| `gemini-2.5-pro`             | 1M tokens      | Base model              |
| `gemini-3-pro-preview`       | 1M tokens      | Preview model           |
| `gemini-2.5-pro-maxthinking` | 1M tokens      | Maximum thinking budget |
| `gemini-2.5-pro-nothinking`  | 1M tokens      | No thinking mode        |
| `gemini-2.5-pro-search`      | 1M tokens      | Search-enhanced         |

#### Antigravity Claude Models

| Model ID                   | Alias             | Extended Thinking |
| -------------------------- | ----------------- | ----------------- |
| `claude-sonnet-4-20250514` | `claude-sonnet-4` | No                |
| `claude-opus-4-20250514`   | `claude-opus-4`   | No                |
| `claude-opus-4-5-20250514` | `claude-opus-4-5` | Yes               |

### Special Model Variants

| Suffix/Prefix | Example                     | Description               |
| ------------- | --------------------------- | ------------------------- |
| `-假流式`     | `gemini-2.5-pro-假流式`     | Fake streaming mode       |
| `流式抗截断/` | `流式抗截断/gemini-2.5-pro` | Anti-truncation streaming |

### Core Module Reference

| Module                  | File                              | Description                                  |
| ----------------------- | --------------------------------- | -------------------------------------------- |
| **OpenAI Router**       | `openai_router.py`                | `/v1/chat/completions` endpoint handling     |
| **Gemini Router**       | `gemini_router.py`                | Gemini native endpoint handling              |
| **Antigravity Router**  | `antigravity_router.py`           | Antigravity OpenAI/Gemini endpoints          |
| **Anthropic Router**    | `antigravity_anthropic_router.py` | `/v1/messages` Claude Code endpoint          |
| **Format Detector**     | `format_detector.py`              | Auto-detect OpenAI vs Gemini format          |
| **OpenAI Transfer**     | `openai_transfer.py`              | OpenAI <-> Gemini format conversion          |
| **Anthropic Converter** | `anthropic_converter.py`          | Anthropic <-> Gemini format conversion       |
| **Anthropic Streaming** | `anthropic_streaming.py`          | Gemini SSE -> Anthropic SSE conversion       |
| **Anthropic Helpers**   | `anthropic_helpers.py`            | `remove_nulls_for_tool_input()`, debug utils |
| **Credential Manager**  | `credential_manager.py`           | OAuth rotation, health monitoring            |
| **State Manager**       | `state_manager.py`                | Atomic state operations, TOML persistence    |
| **Task Manager**        | `task_manager.py`                 | Async task lifecycle management              |
| **Token Estimator**     | `token_estimator.py`              | Input token estimation                       |
| **Anti-Truncation**     | `anti_truncation.py`              | Response truncation detection and retry      |
| **Storage Adapter**     | `storage_adapter.py`              | SQLite/MongoDB abstraction layer             |
| **Web Routes**          | `web_routes.py`                   | REST API and WebSocket endpoints             |
| **Auth**                | `auth.py`                         | OAuth 2.0 flows, JWT management              |

---

## Installation

### Quick Install Scripts

#### Linux

```bash
curl -o install.sh "https://raw.githubusercontent.com/su-kaka/gcli2api/refs/heads/master/install.sh" && chmod +x install.sh && ./install.sh
```

#### macOS

```bash
curl -o darwin-install.sh "https://raw.githubusercontent.com/su-kaka/gcli2api/refs/heads/master/darwin-install.sh" && chmod +x darwin-install.sh && ./darwin-install.sh
```

#### Windows (PowerShell)

```powershell
iex (iwr "https://raw.githubusercontent.com/su-kaka/gcli2api/refs/heads/master/install.ps1" -UseBasicParsing).Content
```

#### Termux (Android)

```bash
curl -o termux-install.sh "https://raw.githubusercontent.com/su-kaka/gcli2api/refs/heads/master/termux-install.sh" && chmod +x termux-install.sh && ./termux-install.sh
```

### Docker

#### Basic Docker Run

```bash
# Single password mode
docker run -d --name gcli2api \
  --network host \
  -e PASSWORD=pwd \
  -e PORT=7861 \
  -v $(pwd)/data/creds:/app/creds \
  ghcr.io/su-kaka/gcli2api:latest

# Separate API and panel passwords
docker run -d --name gcli2api \
  --network host \
  -e API_PASSWORD=api_pwd \
  -e PANEL_PASSWORD=panel_pwd \
  -e PORT=7861 \
  -v $(pwd)/data/creds:/app/creds \
  ghcr.io/su-kaka/gcli2api:latest
```

#### Docker for macOS (no host networking)

```bash
docker run -d \
  --name gcli2api \
  -p 7861:7861 \
  -p 8080:8080 \
  -e PASSWORD=pwd \
  -e PORT=7861 \
  -v "$(pwd)/data/creds":/app/creds \
  ghcr.io/su-kaka/gcli2api:latest
```

#### Docker Compose

```yaml
version: "3.8"

services:
  gcli2api:
    image: ghcr.io/su-kaka/gcli2api:latest
    container_name: gcli2api
    restart: unless-stopped
    network_mode: host
    environment:
      - PASSWORD=pwd
      - PORT=7861
      # Or use separate passwords:
      # - API_PASSWORD=your_api_password
      # - PANEL_PASSWORD=your_panel_password
    volumes:
      - ./data/creds:/app/creds
    healthcheck:
      test: ["CMD-SHELL", 'python -c "import sys, urllib.request, os; port = os.environ.get(''PORT'', ''7861''); req = urllib.request.Request(f''http://localhost:{port}/v1/models'', headers={''Authorization'': ''Bearer '' + os.environ.get(''PASSWORD'', ''pwd'')}); sys.exit(0 if urllib.request.urlopen(req, timeout=5).getcode() == 200 else 1)"']
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
```

### Manual Installation

```bash
# Clone repository
git clone https://github.com/su-kaka/gcli2api.git
cd gcli2api

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e .

# Start server
python web.py
```

### Starting the Server

```bash
# Linux/macOS
cd gcli2api
bash start.sh

# Windows
# Double-click start.bat

# Termux
cd gcli2api
bash termux-start.sh

# Manual
source .venv/bin/activate
python web.py
```

---

## Configuration

### Initial Setup

1. Access the web console at `http://127.0.0.1:7861/auth`
2. Login with default password: `pwd`
3. Complete OAuth authentication:
   - **GCLI Mode**: Google Cloud Gemini API credentials
   - **Antigravity Mode**: Google Antigravity API credentials

### Client Configuration

#### OpenAI-Compatible Clients

```
Endpoint: http://127.0.0.1:7861/v1
API Key: pwd (or your configured password)
```

#### Gemini Native Clients

```
Endpoint: http://127.0.0.1:7861
Authentication (choose one):
  - Authorization: Bearer your_api_password
  - x-goog-api-key: your_api_password
  - URL parameter: ?key=your_api_password
```

#### Claude Code CLI

See [Claude Code Integration](#claude-code-integration-antigravity2claudecode) section.

---

## API Reference

### OpenAI Compatible Endpoint

**POST** `/v1/chat/completions`

Supports both OpenAI and Gemini request formats with auto-detection.

#### OpenAI Format Request

```json
{
  "model": "gemini-2.5-pro",
  "messages": [
    { "role": "system", "content": "You are a helpful assistant" },
    { "role": "user", "content": "Hello" }
  ],
  "temperature": 0.7,
  "stream": true
}
```

#### Gemini Format Request

```json
{
  "model": "gemini-2.5-pro",
  "contents": [{ "role": "user", "parts": [{ "text": "Hello" }] }],
  "systemInstruction": {
    "parts": [{ "text": "You are a helpful assistant" }]
  },
  "generationConfig": {
    "temperature": 0.7
  }
}
```

### Gemini Native Endpoints

**POST** `/v1/models/{model}:generateContent` (non-streaming)
**POST** `/v1/models/{model}:streamGenerateContent` (streaming)
**GET** `/v1/models` (list models)

```bash
curl -X POST "http://127.0.0.1:7861/v1/models/gemini-2.5-pro:generateContent" \
  -H "x-goog-api-key: your_api_password" \
  -H "Content-Type: application/json" \
  -d '{
    "contents": [
      {"role": "user", "parts": [{"text": "Hello"}]}
    ]
  }'
```

### Antigravity Endpoints

**POST** `/antigravity/v1/chat/completions` (OpenAI format)
**POST** `/antigravity/v1/models/{model}:generateContent` (Gemini format)
**POST** `/antigravity/v1/models/{model}:streamGenerateContent` (Gemini streaming)

### Anthropic Messages Endpoint

**POST** `/v1/messages`
**POST** `/v1/messages/count_tokens`

See [Claude Code Integration](#claude-code-integration-antigravity2claudecode) for details.

### Multimodal Support

```json
{
  "model": "gemini-2.5-pro",
  "messages": [
    {
      "role": "user",
      "content": [
        { "type": "text", "text": "Describe this image" },
        {
          "type": "image_url",
          "image_url": {
            "url": "data:image/jpeg;base64,/9j/4AAQSkZJRgABA..."
          }
        }
      ]
    }
  ]
}
```

### Thinking Mode

```json
{
  "model": "gemini-2.5-pro-maxthinking",
  "messages": [{ "role": "user", "content": "Complex math problem" }]
}
```

Response includes separated thinking content:

```json
{
  "choices": [
    {
      "message": {
        "role": "assistant",
        "content": "Final answer",
        "reasoning_content": "Detailed thinking process..."
      }
    }
  ]
}
```

### Web Console API

#### Authentication

| Method | Endpoint                    | Description             |
| ------ | --------------------------- | ----------------------- |
| POST   | `/auth/login`               | User login              |
| POST   | `/auth/start`               | Start GCLI OAuth        |
| POST   | `/auth/antigravity/start`   | Start Antigravity OAuth |
| POST   | `/auth/callback`            | OAuth callback          |
| GET    | `/auth/status/{project_id}` | Check auth status       |

#### GCLI Credential Management

| Method | Endpoint                        | Description               |
| ------ | ------------------------------- | ------------------------- |
| GET    | `/creds/status`                 | Get all credential status |
| POST   | `/creds/action`                 | Single credential action  |
| POST   | `/creds/batch-action`           | Batch credential actions  |
| POST   | `/auth/upload`                  | Upload credentials (ZIP)  |
| GET    | `/creds/download/{filename}`    | Download credential       |
| GET    | `/creds/download-all`           | Download all credentials  |
| POST   | `/creds/fetch-email/{filename}` | Fetch user email          |
| POST   | `/creds/refresh-all-emails`     | Refresh all emails        |

#### Antigravity Credential Management

| Method | Endpoint                                 | Description               |
| ------ | ---------------------------------------- | ------------------------- |
| GET    | `/antigravity/creds/status`              | Get all credential status |
| POST   | `/antigravity/creds/action`              | Single credential action  |
| POST   | `/antigravity/creds/batch-action`        | Batch credential actions  |
| POST   | `/antigravity/auth/upload`               | Upload credentials (ZIP)  |
| GET    | `/antigravity/creds/download/{filename}` | Download credential       |
| GET    | `/antigravity/creds/download-all`        | Download all credentials  |

#### Configuration & Logs

| Method    | Endpoint              | Description          |
| --------- | --------------------- | -------------------- |
| GET       | `/config/get`         | Get current config   |
| POST      | `/config/save`        | Save config          |
| POST      | `/auth/logs/clear`    | Clear logs           |
| GET       | `/auth/logs/download` | Download log file    |
| WebSocket | `/auth/logs/stream`   | Real-time log stream |

#### Usage Statistics

| Method | Endpoint               | Description          |
| ------ | ---------------------- | -------------------- |
| GET    | `/usage/stats`         | Get usage statistics |
| GET    | `/usage/aggregated`    | Get aggregated stats |
| POST   | `/usage/update-limits` | Update usage limits  |
| POST   | `/usage/reset`         | Reset usage stats    |

---

## Claude Code Integration (antigravity2claudecode)

### Architecture

```mermaid
flowchart LR
    subgraph Client["Claude Code (CLI)"]
        CC[Claude Code]
    end

    subgraph Proxy["gcli2api Server :7861"]
        Router[antigravity_anthropic_router]
        Converter[anthropic_converter]
        Streaming[anthropic_streaming]
        API[antigravity_api]
        CredMgr[credential_manager]
    end

    subgraph Google["Google Cloud"]
        AG[Antigravity API]
    end

    CC -->|"POST /v1/messages<br/>Anthropic Format"| Router
    Router --> Converter
    Converter -->|"Gemini Format"| API
    API -->|"OAuth + Request"| AG
    AG -->|"Gemini SSE"| Streaming
    Streaming -->|"Anthropic SSE"| CC
    CredMgr -.->|"Credential Rotation"| API
```

### Quick Setup

#### Step 1: Import Antigravity Credentials

```bash
cd /path/to/gcli2api
source .venv/bin/activate

# Method 1: Script import
python3 << 'EOF'
import asyncio, glob, json
from src.storage_adapter import get_storage_adapter

async def import_creds():
    adapter = await get_storage_adapter()
    for f in glob.glob("creds/ag_*.json"):
        with open(f) as fh:
            data = json.load(fh)
        await adapter.store_credential(f.split('/')[-1], data, is_antigravity=True)
        print(f"Imported: {f}")

asyncio.run(import_creds())
EOF

# Method 2: Web interface
# Visit http://localhost:7861/auth and upload ZIP file
```

#### Step 2: Configure Shell Alias

```bash
cat >> ~/.bashrc << 'EOF'

# === gcli2api + Claude Code (antigravity2claudecode) ===
alias gcli='cd /path/to/gcli2api && source .venv/bin/activate && python web.py'

gclaude() {
    ANTHROPIC_AUTH_TOKEN="" \
    ANTHROPIC_BASE_URL="http://localhost:7861" \
    ANTHROPIC_API_KEY="pwd" \
    claude "$@"
}
EOF

source ~/.bashrc
```

#### Step 3: Run

```bash
# Terminal 1: Start gcli2api server
gcli

# Terminal 2: Start Claude Code
gclaude
```

### Environment Variables for Claude Code

| Variable               | Description                                | Required |
| ---------------------- | ------------------------------------------ | -------- |
| `ANTHROPIC_BASE_URL`   | gcli2api server address                    | Yes      |
| `ANTHROPIC_API_KEY`    | API password (matches gcli2api `PASSWORD`) | Yes      |
| `ANTHROPIC_AUTH_TOKEN` | Must be empty string to disable OAuth      | Yes      |

### Extended Thinking Support

gcli2api fully supports Claude's Extended Thinking feature:

```json
{
  "model": "claude-opus-4-5-20250514",
  "max_tokens": 16000,
  "thinking": {
    "type": "enabled",
    "budget_tokens": 10000
  },
  "messages": [{ "role": "user", "content": "Solve this complex problem..." }]
}
```

#### Thinking Processing Logic

| Condition                                               | Behavior                                                           |
| ------------------------------------------------------- | ------------------------------------------------------------------ |
| `client_thinking_enabled=True`                          | Output thinking blocks as-is (`content_block_start` type=thinking) |
| `client_thinking_enabled=False, thinking_to_text=True`  | Convert thinking to `<assistant_thinking>` wrapped text            |
| `client_thinking_enabled=False, thinking_to_text=False` | Filter out thinking content completely                             |

### Streaming Response Event Sequence

```
event: message_start
data: {"type":"message_start","message":{"id":"msg_xxx","model":"claude-opus-4-5",...}}

event: content_block_start
data: {"type":"content_block_start","index":0,"content_block":{"type":"thinking","thinking":""}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"thinking_delta","thinking":"Let me analyze..."}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"signature_delta","signature":"..."}}

event: content_block_stop
data: {"type":"content_block_stop","index":0}

event: content_block_start
data: {"type":"content_block_start","index":1,"content_block":{"type":"text","text":""}}

event: content_block_delta
data: {"type":"content_block_delta","index":1,"delta":{"type":"text_delta","text":"Based on my analysis..."}}

event: content_block_stop
data: {"type":"content_block_stop","index":1}

event: message_delta
data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"input_tokens":100,"output_tokens":500}}

event: message_stop
data: {"type":"message_stop"}
```

### Tool Use Support

```json
{
  "model": "claude-sonnet-4-20250514",
  "max_tokens": 1024,
  "tools": [
    {
      "name": "get_weather",
      "description": "Get current weather",
      "input_schema": {
        "type": "object",
        "properties": {
          "location": { "type": "string" }
        },
        "required": ["location"]
      }
    }
  ],
  "messages": [{ "role": "user", "content": "What's the weather in Tokyo?" }]
}
```

Tool use response handling:

- Auto-generates `tool_use` blocks with `id`, `name`, `input`
- `input` field auto-cleans null values (prevents downstream parsing errors)
- `stop_reason` auto-set to `"tool_use"`

### Testing

```bash
# Test API endpoint
curl -X POST http://localhost:7861/v1/messages \
  -H "Content-Type: application/json" \
  -H "x-api-key: pwd" \
  -d '{
    "model": "claude-sonnet-4-20250514",
    "max_tokens": 100,
    "messages": [{"role": "user", "content": "Hello!"}]
  }'

# Test token counting
curl -X POST http://localhost:7861/v1/messages/count_tokens \
  -H "Content-Type: application/json" \
  -H "x-api-key: pwd" \
  -d '{
    "model": "claude-sonnet-4-20250514",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

### Debug Mode

```bash
export ANTHROPIC_DEBUG=1
export ANTHROPIC_DEBUG_BODY=1  # Print request/response bodies (may be large)

gcli
```

### Test Coverage

```bash
# Run all tests
make test

# Run thinking-related tests (80% coverage required)
make test-thinking

# View coverage report
make test-cov
```

| Module                            | Test File                    | Coverage |
| --------------------------------- | ---------------------------- | -------- |
| `anthropic_streaming.py`          | `test_streaming_thinking.py` | 86%      |
| `antigravity_anthropic_router.py` | `test_router_helpers.py`     | 80%+     |
| `anthropic_converter.py`          | `test_thinking_handling.py`  | 80%+     |

---

## Storage Backends

### SQLite (Default)

- No configuration required
- Data stored in local SQLite database
- Suitable for single-machine deployments
- Auto-creates and manages database files

### MongoDB (Cloud/Distributed)

Enable MongoDB for multi-instance or cloud deployments.

#### Configuration

```bash
# Local MongoDB
export MONGODB_URI="mongodb://localhost:27017"

# MongoDB Atlas
export MONGODB_URI="mongodb+srv://username:password@cluster.mongodb.net"

# With authentication
export MONGODB_URI="mongodb://admin:password@localhost:27017/admin"

# Custom database name (default: gcli2api)
export MONGODB_DATABASE="my_gcli_db"
```

#### Docker with MongoDB

```bash
docker run -d --name gcli2api \
  -e MONGODB_URI="mongodb://mongodb:27017" \
  -e API_PASSWORD=your_password \
  --network your_network \
  ghcr.io/su-kaka/gcli2api:latest
```

#### Docker Compose with MongoDB

```yaml
version: "3.8"

services:
  mongodb:
    image: mongo:7
    container_name: gcli2api-mongodb
    restart: unless-stopped
    environment:
      MONGO_INITDB_ROOT_USERNAME: admin
      MONGO_INITDB_ROOT_PASSWORD: password123
    volumes:
      - mongodb_data:/data/db
    ports:
      - "27017:27017"

  gcli2api:
    image: ghcr.io/su-kaka/gcli2api:latest
    container_name: gcli2api
    restart: unless-stopped
    depends_on:
      - mongodb
    environment:
      - MONGODB_URI=mongodb://admin:password123@mongodb:27017/admin
      - MONGODB_DATABASE=gcli2api
      - API_PASSWORD=your_api_password
      - PORT=7861
    ports:
      - "7861:7861"

volumes:
  mongodb_data:
```

#### Advanced MongoDB Configuration

```bash
# Connection pool and timeout
export MONGODB_URI="mongodb://localhost:27017?maxPoolSize=10&serverSelectionTimeoutMS=5000"

# Replica set
export MONGODB_URI="mongodb://host1:27017,host2:27017,host3:27017/gcli2api?replicaSet=myReplicaSet"

# Read/write separation
export MONGODB_URI="mongodb://localhost:27017/gcli2api?readPreference=secondaryPreferred"
```

---

## Environment Variables

### Basic Configuration

| Variable | Default   | Description         |
| -------- | --------- | ------------------- |
| `PORT`   | `7861`    | Server port         |
| `HOST`   | `0.0.0.0` | Server bind address |

### Password Configuration

| Variable         | Default             | Description                               |
| ---------------- | ------------------- | ----------------------------------------- |
| `PASSWORD`       | `pwd`               | Universal password (overrides both below) |
| `API_PASSWORD`   | inherits `PASSWORD` | Chat API access password                  |
| `PANEL_PASSWORD` | inherits `PASSWORD` | Control panel access password             |

### Performance & Stability

| Variable                       | Default | Description                      |
| ------------------------------ | ------- | -------------------------------- |
| `CALLS_PER_ROTATION`           | `10`    | Calls before credential rotation |
| `RETRY_429_ENABLED`            | `true`  | Enable 429 error auto-retry      |
| `RETRY_429_MAX_RETRIES`        | `3`     | Max 429 retry attempts           |
| `RETRY_429_INTERVAL`           | `1.0`   | 429 retry interval (seconds)     |
| `ANTI_TRUNCATION_MAX_ATTEMPTS` | `3`     | Max anti-truncation retries      |

### Network & Proxy

| Variable               | Default | Description                           |
| ---------------------- | ------- | ------------------------------------- |
| `PROXY`                | -       | HTTP/HTTPS proxy (`http://host:port`) |
| `OAUTH_PROXY_URL`      | -       | OAuth authentication proxy endpoint   |
| `GOOGLEAPIS_PROXY_URL` | -       | Google APIs proxy endpoint            |
| `METADATA_SERVICE_URL` | -       | Metadata service proxy endpoint       |

### Automation

| Variable              | Default | Description                          |
| --------------------- | ------- | ------------------------------------ |
| `AUTO_BAN`            | `true`  | Enable credential auto-ban           |
| `AUTO_LOAD_ENV_CREDS` | `false` | Auto-load env credentials on startup |

### Compatibility

| Variable             | Default | Description                              |
| -------------------- | ------- | ---------------------------------------- |
| `COMPATIBILITY_MODE` | `false` | Convert system messages to user messages |

### Logging

| Variable    | Default        | Description                          |
| ----------- | -------------- | ------------------------------------ |
| `LOG_LEVEL` | `INFO`         | Log level (DEBUG/INFO/WARNING/ERROR) |
| `LOG_FILE`  | `gcli2api.log` | Log file path                        |

### Storage

| Variable           | Default    | Description                                      |
| ------------------ | ---------- | ------------------------------------------------ |
| `MONGODB_URI`      | -          | MongoDB connection string (enables MongoDB mode) |
| `MONGODB_DATABASE` | `gcli2api` | MongoDB database name                            |

### Debug (Anthropic)

| Variable               | Default | Description                      |
| ---------------------- | ------- | -------------------------------- |
| `ANTHROPIC_DEBUG`      | -       | Enable verbose Anthropic logging |
| `ANTHROPIC_DEBUG_BODY` | -       | Print request/response bodies    |

---

## Troubleshooting

### Common Issues

| Issue                    | Cause               | Solution                                                   |
| ------------------------ | ------------------- | ---------------------------------------------------------- |
| OAuth fails              | Not on localhost    | Complete OAuth on localhost first, then upload credentials |
| 429 errors               | Rate limited        | Enable `RETRY_429_ENABLED`, add more credentials           |
| Truncated responses      | Response too long   | Use `流式抗截断/` prefix on model name                     |
| Connection refused       | Server not running  | Start server with `python web.py`                          |
| Invalid credentials      | Expired OAuth token | Re-authenticate or check credential status                 |
| MongoDB connection fails | Wrong URI           | Verify `MONGODB_URI` format and connectivity               |

### Debug Commands

```bash
# Check server status
curl http://localhost:7861/v1/models -H "Authorization: Bearer pwd"

# View credential status
curl http://localhost:7861/creds/status -H "Authorization: Bearer pwd"

# Enable debug logging
export LOG_LEVEL=DEBUG
python web.py
```

### Log Locations

- **Server logs**: `gcli2api.log` (or `LOG_FILE` path)
- **Real-time logs**: WebSocket at `/auth/logs/stream`
- **Download logs**: GET `/auth/logs/download`

---

## License

**Cooperative Non-Commercial License (CNC-1.0)**

### Allowed Uses

- Personal learning, research, education
- Non-profit organization use
- Open source project integration (same license)
- Academic research and publications

### Prohibited Uses

- Any commercial use
- Use by companies with >$1M annual revenue
- VC-backed or publicly traded companies
- Paid services or products
- Commercial competition

See [LICENSE](LICENSE) for full terms.

---

## Disclaimer

This project is for learning and research purposes only. By using this project, you agree to:

- Not use for any commercial purposes
- Assume all risks and responsibilities
- Comply with relevant terms of service and laws

The project authors are not liable for any direct or indirect damages arising from use of this project.

---

## Community

**QQ Group: 937681997**

<img src="docs/qq群.jpg" width="200" alt="QQ Group QR Code">

---

## Support

If this project helps you, consider supporting its continued development!

See [Donation Guide](docs/DONATE.md) for details.
