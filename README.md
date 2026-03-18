# Onboard Assist

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![CI](https://github.com/theadityamittal/onboard-assist/actions/workflows/ci.yml/badge.svg)](https://github.com/theadityamittal/onboard-assist/actions)
[![Coverage: 99%](https://img.shields.io/badge/coverage-99%25-brightgreen.svg)]()

Adaptive AI-driven Slack bot that onboards volunteers at nonprofit organizations. Asks intake questions, generates a personalized plan, walks through it conversationally using the org's knowledge base, and takes real actions — assigning Slack channels, creating calendar events, and tracking progress across sessions.

Built as a generic platform with [Changing the Present](https://changingthepresent.org) as the demo tenant.

## Problem

Nonprofit volunteer onboarding is manual, inconsistent, and time-consuming. New volunteers get different information depending on who onboards them, team leads repeat the same orientation dozens of times, and there's no tracking of who completed what.

## How It Works

```
1. Workspace admin installs via "Add to Slack" OAuth flow
2. Admin provides org website URL → bot scrapes and indexes the knowledge base
3. New volunteer joins workspace → bot DMs them automatically
4. Intake questions determine role and experience level
5. Personalized onboarding plan generated (5-8 steps)
6. Bot walks through plan conversationally:
   - Answers questions from the knowledge base (RAG)
   - Assigns volunteer to relevant Slack channels
   - Creates orientation meeting on Google Calendar
   - Tracks progress, resumes across sessions
   - Adapts the plan when context changes
7. Completion record saved for audit trail
```

## Architecture

```
                         ┌──────────────────────────────┐
                         │     API Gateway (REST)        │
                         │  5 routes (Slack + OAuth)     │
                         └──────┬───────────────┬───────┘
                                │               │
                     events/commands        OAuth callbacks
                                │               │
                                v               v
                         ┌────────────┐  ┌────────────┐  ┌────────────┐
                         │   Slack    │  │Slack OAuth │  │Google OAuth│
                         │  Handler   │  │  Lambda    │  │  Callback  │
                         │  Lambda    │  │            │  │  Lambda    │
                         └─────┬──────┘  └────────────┘  └────────────┘
                               │
                    signature verify
                    middleware chain
                    enqueue to SQS
                               │
                               v
                         ┌────────────┐       ┌────────────┐
                         │  SQS FIFO  │──────>│  SQS DLQ   │
                         │  Queue     │       │  (3 fails) │
                         └─────┬──────┘       └────────────┘
                               │
                               v
┌──────────────────────────────────────────────────────────────────┐
│                      Agent Worker Lambda                         │
│                                                                  │
│  Orchestrator (Plan + ReAct + Tool Calling)                      │
│      │                                                           │
│      ├── search_kb ──────────────────────────────> Pinecone      │
│      ├── send_message ───────────────────────────> Slack API     │
│      ├── assign_channel ─────────────────────────> Slack API     │
│      ├── calendar_event ─────────────────────────> Google Cal    │
│      └── manage_progress ────────────────────────> DynamoDB      │
│                                                                  │
│  LLM Router: Nova Micro (reasoning) + Haiku (generation)         │
│  Agent Middleware: turn budget, tool validator, output validator   │
└──────────────────────────────────────────────────────────────────┘

Supporting: DynamoDB (state) | S3 (docs) | Secrets Manager | CloudWatch
Scheduled: Health Check (daily) | Nudge (daily) | Kill Switch (budget SNS)
```

### Seven Lambda Functions

| Lambda | Trigger | Purpose |
|---|---|---|
| Slack Handler | API Gateway POST | Parse events, run inbound middleware, enqueue to SQS |
| Slack OAuth | API Gateway GET | Exchange auth code for bot token, store in DynamoDB |
| Google OAuth | API Gateway GET | Exchange auth code for refresh token, resume blocked steps |
| Agent Worker | SQS FIFO | Process messages, run orchestrator, reply via Slack |
| Kill Switch | SNS (budget alarm) | Disable API Gateway, set DynamoDB flag |
| Health Check | EventBridge (daily 8am) | Ping Pinecone index, recreate if paused |
| Nudge | EventBridge (daily 2pm) | DM inactive users after 7 days |

### Inbound Middleware Chain

Ordered cheapest to most expensive — short-circuits on first rejection:

| # | Middleware | Cost | On Failure |
|---|---|---|---|
| 1 | Signature Verification | CPU | Reject (forged request) |
| 2 | Bot Filter | CPU | Drop (prevent self-loops) |
| 3 | Empty Filter | CPU | Drop (blank messages) |
| 4 | Rate Limiter | 1 DynamoDB write | Respond ("Still working on your previous message...") |
| 5 | Input Sanitizer | CPU + conditional write | Respond ("I can only help with onboarding questions") |
| 6 | Token Budget Guard | 2 DynamoDB reads | Respond ("Daily/monthly limit reached") |

### Agent Orchestration

Hybrid **Plan + ReAct + Tool Calling** architecture:

- **Plan phase** — LLM creates personalized onboarding plan from intake answers
- **Execute phase** — each step uses structured tool calls (search KB, send message, etc.)
- **ReAct reasoning** — on unexpected input, LLM reasons explicitly before acting
- **Incremental replanning** — only pending steps modified; completed steps frozen

**Two-model split** minimizes cost:

| Call Type | Model | Purpose |
|---|---|---|
| Reasoning | Amazon Nova Micro | "What should I do next?" |
| Generation | Claude 3.5 Haiku | "Generate the response" |

### Three-Layer Cost Protection

```
Layer 3: Workspace monthly cap ($5)     ← protects AWS bill
  Layer 2: User daily cap (50 turns)    ← prevents one user hogging resources
    Layer 1: Per-turn budget            ← prevents runaway agent loops

  + AWS Budget ($10) + Kill Switch      ← nuclear option
```

## Tech Stack

| Layer | Technology |
|---|---|
| Runtime | Python 3.12, AWS Lambda (arm64) |
| Infrastructure | AWS SAM / CloudFormation, GitHub Actions CI/CD |
| Queue | SQS FIFO (per-user ordering, event deduplication) |
| State | DynamoDB (single-table design, TTL policies) |
| LLM | Amazon Bedrock (Nova Micro + Claude Haiku) |
| Vector Search | Pinecone (namespaces for multi-tenancy, hybrid search, reranking) |
| Storage | S3 (versioned raw HTML archive) |
| Secrets | AWS Secrets Manager (3 secrets) |
| Monitoring | CloudWatch (logs, metrics, alarms), X-Ray tracing |
| Slack | slack-sdk, Events API, Block Kit, OAuth2 |
| Calendar | Google Calendar API, OAuth2 |
| Testing | pytest, moto, TDD, 90%+ coverage gate |
| Linting | ruff, mypy, pre-commit hooks |

### Estimated Monthly Cost

| Component | Cost |
|---|---|
| Lambda, API Gateway, SQS, DynamoDB, S3, CloudWatch, EventBridge, SNS | $0 (free tier) |
| Bedrock (Nova Micro + Claude Haiku) | $0.05 - $2.00 |
| Secrets Manager (3 secrets) | $1.20 |
| Pinecone, Google Calendar API, Slack Platform | $0 (free tiers) |
| **Total** | **$1 - $3/month** |

Hard cap: $10/month via AWS Budgets + Kill Switch Lambda.

## Project Structure

```
onboard-assist/
├── src/
│   ├── config/
│   │   └── settings.py              # Pydantic Settings, env-based config
│   ├── slack/
│   │   ├── handler.py               # Slack Handler Lambda (events + commands + interactions)
│   │   ├── oauth.py                 # Slack OAuth Lambda
│   │   ├── models.py                # Frozen dataclasses (SlackEvent, SlackCommand, SQSMessage)
│   │   ├── signature.py             # HMAC-SHA256 signature verification
│   │   ├── client.py                # Slack API wrapper
│   │   └── commands.py              # Slash command handlers
│   ├── middleware/
│   │   ├── inbound/                 # Pre-SQS: signature, filters, rate limiter, sanitizer, budget
│   │   └── agent/                   # Per-LLM-call: output validator, tool validator, turn budget
│   ├── agent/
│   │   ├── worker.py                # Agent Worker Lambda
│   │   ├── orchestrator.py          # Plan + ReAct + Tool Calling engine
│   │   ├── planner.py               # Plan generation + incremental replanning
│   │   ├── tools/                   # search_kb, send_message, assign_channel, calendar_event, manage_progress
│   │   └── prompts/                 # System, planner, and responder prompts
│   ├── rag/
│   │   ├── pipeline.py              # Scrape → S3 → chunk → embed → Pinecone
│   │   ├── vectorstore.py           # Pinecone client (namespaces, hybrid search, rerank)
│   │   ├── chunker.py               # Document chunking with overlap
│   │   ├── confidence.py            # 4-factor confidence scoring
│   │   ├── scraper.py               # Web scraper (robots.txt compliant)
│   │   └── storage.py               # S3 raw HTML + manifest storage
│   ├── llm/
│   │   ├── provider.py              # LLM provider interface
│   │   ├── bedrock.py               # Bedrock provider (Nova Micro + Claude Haiku)
│   │   ├── router.py                # Model router + cost tracking
│   │   └── fallback.py              # Fallback chain
│   ├── state/
│   │   ├── dynamo.py                # DynamoDB single-table operations
│   │   ├── models.py                # Frozen dataclasses (Plan, Steps, Usage, WorkspaceConfig)
│   │   └── ttl.py                   # TTL policies (60s locks → 90d plans → permanent completions)
│   ├── gcal/
│   │   └── callback.py              # Google OAuth Callback Lambda
│   └── admin/
│       ├── kill_switch.py           # Kill Switch Lambda (SNS → disable API Gateway)
│       ├── health_check.py          # Pinecone health check Lambda (daily cron)
│       └── nudge.py                 # Inactivity nudge Lambda (daily cron)
├── tests/
│   ├── unit/                        # Per-module unit tests
│   ├── integration/                 # Mocked AWS integration tests
│   └── conftest.py                  # Shared fixtures
├── infra/
│   ├── template.yaml                # SAM template (all 46 AWS resources)
│   └── policies/
│       └── deploy-policy.json       # Least-privilege IAM for GitHub Actions OIDC
├── .github/workflows/ci.yml         # Lint → test → coverage gate → SAM validate → deploy
├── .pre-commit-config.yaml          # ruff, ruff-format, mypy, pytest, sam-validate
├── samconfig.toml
└── pyproject.toml
```

## DynamoDB Single-Table Design

| pk | sk | Purpose | TTL |
|---|---|---|---|
| `WORKSPACE#{id}` | `CONFIG` | Workspace config (org name, bot token, channels) | — |
| `WORKSPACE#{id}` | `PLAN#{user_id}` | Active onboarding plan + context | 90 days |
| `WORKSPACE#{id}` | `COMPLETED#{user_id}` | Completion record (audit trail) | Never |
| `WORKSPACE#{id}` | `USAGE#{user_id}#{date}` | Per-user daily usage | 7 days |
| `WORKSPACE#{id}` | `USAGE#{yyyy-mm}` | Per-workspace monthly usage | 30 days |
| `WORKSPACE#{id}` | `LOCK#{user_id}` | Processing lock | 60 seconds |
| `WORKSPACE#{id}` | `OAUTH#GOOGLE#{user_id}` | Google Calendar tokens | 90 days |
| `WORKSPACE#{id}` | `OAUTH#SLACK` | Slack bot token | — |
| `SYSTEM` | `KILL_SWITCH` | Global kill switch flag | — |
| `SECURITY` | `INJECTION#{ts}` | Injection attempt logs | 90 days |

## Security

- Slack signature verification (HMAC-SHA256) on every request
- Prompt injection detection with regex patterns + strike counter (3 strikes → silent drop)
- Output validation blocks system prompt leaks and persona breaks
- Tool call validation (allowed names, param constraints, per-turn limits)
- IAM least-privilege per Lambda function
- Secrets in Secrets Manager (never in env vars or code)
- DynamoDB encryption at rest
- No VPC required — all external services use HTTPS + API key auth

## Development

```bash
# Install
pip install -e ".[dev]"

# Run tests (TDD, 90%+ coverage enforced)
pytest

# Lint + format + type check
ruff check src/ tests/
ruff format --check src/ tests/
mypy src/

# Pre-commit (runs all of the above + sam validate)
pre-commit run --all-files

# SAM build + validate
sam build
sam validate --template infra/template.yaml --lint

# Deploy (requires AWS credentials with deploy-policy.json)
sam deploy
```

## CI/CD

GitHub Actions pipeline on every push/PR to `main`:

1. **Lint** — ruff check + ruff format + mypy
2. **Test** — pytest with 90% coverage gate
3. **SAM Validate** — template linting
4. **Deploy** — SAM deploy via OIDC (gated by `DEPLOY_ENABLED` variable)

## Author

**Aditya Mittal** — [theadityamittal@gmail.com](mailto:theadityamittal@gmail.com)

## License

MIT
