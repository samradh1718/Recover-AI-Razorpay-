# RecoverAI

### Policy-safe, AI-assisted failed-payment recovery for Razorpay

[![Python](https://img.shields.io/badge/Python-3.10-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.141-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white)](https://redis.io/)
[![Celery](https://img.shields.io/badge/Celery-5.6-37814A?logo=celery&logoColor=white)](https://docs.celeryq.dev/)
[![Razorpay](https://img.shields.io/badge/Razorpay-Test_Mode-0C67F5)](https://razorpay.com/)

RecoverAI converts failed Razorpay payments into safe, explainable and auditable recovery journeys.

It verifies provider evidence, creates a Recovery Case, evaluates policy-safe recovery options, escalates uncertain cases to a human operator and executes only an approved recovery action.

> **Safety:** RecoverAI is deliberately restricted to Razorpay Test Mode and moves ₹0 real money.

---

## Problem

A failed payment does not always mean that the customer has lost the intent to pay. However, traditional payment recovery systems often depend on:

- fixed retry schedules;
- limited failure context;
- disconnected operational tools;
- unsafe automated decisions;
- weak customer communication;
- incomplete audit trails.

This results in avoidable revenue loss and a poor customer experience.

## Solution

RecoverAI provides a complete failed-payment recovery control plane:

1. Receive signed webhooks or authenticated Razorpay server evidence.
2. Persist the payment event idempotently.
3. Create a Recovery Case.
4. Classify the failure.
5. Evaluate policy-allowed recovery actions.
6. Compare expected recovery value with intervention cost.
7. Escalate uncertain or high-risk cases to Human Review.
8. Execute only policy-approved or operator-approved actions.
9. Generate a Razorpay Test Mode Payment Link.
10. Notify the customer.
11. Confirm the captured recovery payment from Razorpay.
12. Record the full journey in an auditable timeline.

---

## Verified end-to-end recovery

The complete workflow has been tested through the RecoverAI frontend using Razorpay Test Mode.

| Stage | Verified result |
|---|---|
| Provider order | Created by Razorpay |
| Original amount | ₹1,500 |
| Failed payment | `pay_TWFgnylStON74T` |
| Failure evidence | Provider-confirmed |
| Policy result | Escalated |
| Case state | `HUMAN_REVIEW` |
| Human action | Approved `send_payment_link` |
| Payment Link | `plink_TWFiSyV3qvBRtl` |
| Customer notification | Test email received |
| Recovery payment | `pay_TWFk6vclwGmiqP` |
| Provider status | `paid` |
| Final state | `RECOVERED` |
| Recovered amount | ₹1,500 |
| Intervention cost | ₹1 |
| Net recovered value | ₹1,499 |
| Real money moved | ₹0 |

The identifiers above are Razorpay Test Mode identifiers and contain no API credentials.

---

## Recovery journey

```mermaid
flowchart TD
    A["Razorpay payment fails"] --> B["Provider evidence verified"]
    B --> C["Recovery Case created"]
    C --> D["Rules and policy evaluation"]

    D -->|Safe action| E["Action scheduled"]
    D -->|Uncertain or high risk| F["Human Review"]

    F -->|Approve| E
    F -->|Reject| G["Recovery stopped"]

    E --> H["Razorpay Payment Link"]
    H --> I["Customer notified"]
    I --> J["Customer pays"]
    J --> K["Provider reconciliation"]
    K --> L["Case recovered"]
```

---

## Architecture

```mermaid
flowchart TB
    UI["React Recovery Control Room"]
    API["FastAPI API"]
    DB["PostgreSQL"]
    REDIS["Redis"]
    WORKERS["Celery workers"]
    POLICY["Rules and policy engine"]
    SHADOW["Ollama + ML shadow evaluators"]
    RAZORPAY["Razorpay Test Mode"]

    UI --> API
    API --> DB
    API --> REDIS
    REDIS --> WORKERS
    WORKERS --> POLICY
    WORKERS --> SHADOW
    API --> RAZORPAY
    WORKERS --> RAZORPAY
    WORKERS --> DB
```

| Component | Responsibility |
|---|---|
| React + TypeScript | Live recovery dashboard, Test Checkout and Human Review |
| FastAPI | APIs, validation, tenant isolation and provider integration |
| PostgreSQL | Events, cases, decisions, reviews and audit evidence |
| Redis | Celery broker and task coordination |
| Celery | Event processing, action execution and reconciliation |
| Rules engine | Production decision and policy enforcement |
| Ollama | Independent AI shadow recommendation |
| ML shadow worker | Independent recovery-action ranking |
| Razorpay Test Mode | Checkout, Orders, Payment Links and payment evidence |

---

## Core features

### Razorpay Test Checkout

- Creates an actual Razorpay Test Mode order.
- Opens Razorpay Checkout from the dashboard.
- Persists provider-generated telemetry.
- Restricts credentials to the `rzp_test_` prefix.
- Enforces a configurable demo amount ceiling.
- Never moves real money.

### Provider-confirmed failure ingestion

RecoverAI supports:

- signed Razorpay webhooks; and
- authenticated server-side reconciliation for local Test Checkout.

Provider-confirmed failures are converted into idempotent `payment.failed` events and queued for processing.

### Policy-safe recovery decisions

The production rules engine evaluates:

- failure category;
- recoverable amount;
- recovery deadline;
- previous attempts;
- customer communication count;
- expected recovery value;
- intervention cost;
- high-value thresholds;
- retry and communication limits.

Only policy-authorized decisions can execute.

### Human Review

Cases are escalated when:

- the failure category is unknown;
- a high-value case requires approval;
- the automatic attempt limit is reached;
- the customer contact limit is reached;
- policy cannot safely authorize automation.

An operator can:

- approve a payment retry;
- approve a Payment Link;
- request a payment-method update;
- request customer authorization;
- reject and stop recovery;
- record reviewer identity and reasoning.

State-version checks prevent stale or conflicting approvals.

### Razorpay Payment Link recovery

Approved customer-facing actions can create a Razorpay Test Mode Payment Link.

RecoverAI stores:

- Payment Link ID;
- deterministic reference ID;
- hosted Payment Link URL;
- provider order ID;
- safe provider response evidence;
- notification request status;
- captured recovery payment ID.

### Exact provider reconciliation

A case is marked recovered only after verifying:

- Payment Link identity;
- deterministic provider reference;
- provider status `paid`;
- captured payment evidence;
- currency;
- exact recovered amount.

The original failed payment and successful recovery payment remain separate:

```text
failed_provider_payment_id
recovered_provider_payment_id
```

### AI and ML shadow mode

Ollama and the ML evaluator independently:

- recommend recovery actions;
- estimate recovery probability;
- calculate expected value;
- compare against the production decision;
- measure agreement and latency.

They never execute payment actions or bypass production policy.

### Complete audit timeline

RecoverAI records:

- provider evidence received;
- payment event processed;
- Recovery Case created;
- production decision generated;
- Human Review requested;
- Human Review approved or rejected;
- Human Review decision generated;
- action scheduled;
- action executed;
- Payment Link created;
- customer notification requested;
- provider payment confirmed;
- revenue recovered;
- case closed;
- AI shadow decision;
- ML shadow decision.

---

## Recovery state model

```mermaid
stateDiagram-v2
    [*] --> DETECTED

    DETECTED --> SCHEDULED
    DETECTED --> WAITING_FOR_CUSTOMER
    DETECTED --> HUMAN_REVIEW

    HUMAN_REVIEW --> SCHEDULED: Approve retry
    HUMAN_REVIEW --> WAITING_FOR_CUSTOMER: Approve customer action
    HUMAN_REVIEW --> STOPPED: Reject

    SCHEDULED --> WAITING_FOR_RETRY
    WAITING_FOR_RETRY --> RECOVERED
    WAITING_FOR_CUSTOMER --> RECOVERED

    RECOVERED --> [*]
    STOPPED --> [*]
    EXPIRED --> [*]
    EXHAUSTED --> [*]
```

---

## Technology stack

### Backend

- Python 3.10
- FastAPI
- Pydantic
- SQLAlchemy
- Alembic
- PostgreSQL 16
- Redis 7
- Celery
- HTTPX
- Razorpay SDK
- Pytest

### Frontend

- React 19
- TypeScript
- Vite
- React Router
- Lucide React
- CSS

### Intelligence

- Deterministic rules engine
- Policy guardrails
- Ollama LLM shadow evaluation
- ML shadow evaluation
- Expected-value ranking

### Infrastructure

- Docker Compose
- PostgreSQL container
- Redis container
- Independent Celery queues
- Razorpay Test Mode

---

## Repository structure

```text
razorpay/
├── backend/
│   ├── app/
│   │   ├── api/v1/
│   │   ├── contracts/
│   │   ├── core/
│   │   ├── db/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── services/
│   │   └── workers/
│   ├── migrations/
│   ├── ml/
│   ├── .env.example
│   ├── alembic.ini
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   └── components/
│   └── package.json
├── docs/
├── docker-compose.yml
└── README.md
```

---

## Prerequisites

Install:

- Python 3.10+
- Node.js 20+
- Docker Desktop
- Git
- Ollama
- Razorpay Test Mode account
- Razorpay Test API credentials

Do not use Razorpay Live Mode credentials.

---

## Installation

### 1. Clone the repository

```powershell
git clone https://github.com/samradh1718/Recover-AI-Razorpay-.git

cd Recover-AI-Razorpay-
```

### 2. Start PostgreSQL and Redis

Open Docker Desktop and run:

```powershell
docker compose up -d

docker compose ps
```

Expected containers:

```text
recoverai-database
recoverai-redis
```

### 3. Configure the backend

```powershell
cd backend

py -3.10 -m venv .venv

.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip

pip install -r requirements.txt

Copy-Item .env.example .env
```

Configure `backend/.env`:

```dotenv
APP_NAME=RecoverAI
APP_ENV=demo
APP_DEBUG=true

FRONTEND_ORIGIN=http://localhost:5173
BACKEND_API_BASE_URL=http://127.0.0.1:8000/api/v1

DEMO_TENANT_ID=11111111-1111-1111-1111-111111111111

DATABASE_URL=postgresql+psycopg://recoverai:recoverai@localhost:5433/recoverai
REDIS_URL=redis://localhost:6379/0

RAZORPAY_MODE=test
RAZORPAY_KEY_ID=rzp_test_your_key_id
RAZORPAY_KEY_SECRET=your_test_key_secret
RAZORPAY_WEBHOOK_SECRET=your_test_webhook_secret

RAZORPAY_ACTIONS_ENABLED=true
RAZORPAY_TEST_CHECKOUT_ENABLED=true
RAZORPAY_TEST_CHECKOUT_MAX_AMOUNT_RUPEES=10000

RAZORPAY_CUSTOMER_NOTIFICATIONS_ENABLED=true
RAZORPAY_NOTIFICATION_CHANNEL=email

DEMO_CUSTOMER_EMAIL=your_test_email@example.com
DEMO_CUSTOMER_CONTACT=9999999999

DEMO_ACTION_DELAY_SECONDS=10

RAZORPAY_API_TIMEOUT_SECONDS=20
RAZORPAY_PAYMENT_LINK_EXPIRY_MINUTES=1440

RAZORPAY_RECONCILIATION_ENABLED=true
RAZORPAY_RECONCILIATION_INITIAL_DELAY_SECONDS=30
RAZORPAY_RECONCILIATION_RETRY_DELAY_SECONDS=60
RAZORPAY_RECONCILIATION_MAX_ATTEMPTS=10

AI_SHADOW_MODE_ENABLED=true
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=llama3:latest
OLLAMA_TIMEOUT_SECONDS=120
OLLAMA_PROMPT_VERSION=shadow_v1
```

Important:

- Never commit `.env`.
- Use only `rzp_test_` credentials.
- Environment values do not need quotation marks.
- Use only your own test email and contact.
- Frontend and backend tenant IDs must match.

### 4. Apply database migrations

From the `backend` directory:

```powershell
alembic upgrade head

alembic current

alembic heads
```

### 5. Start Ollama

```powershell
ollama pull llama3:latest

ollama serve
```

### 6. Start FastAPI

```powershell
cd backend

.\.venv\Scripts\Activate.ps1

uvicorn app.main:app `
  --reload `
  --host 127.0.0.1 `
  --port 8000
```

API documentation:

```text
http://127.0.0.1:8000/docs
```

### 7. Start Celery workers

#### Production worker

```powershell
celery -A app.workers.celery_app:celery_app worker `
  --loglevel=info `
  --pool=solo `
  -Q celery `
  -n recoverai-production@%h
```

#### AI shadow worker

```powershell
celery -A app.workers.celery_app:celery_app worker `
  --loglevel=info `
  --pool=solo `
  -Q ai_shadow `
  -n recoverai-ai@%h
```

#### ML shadow worker

```powershell
celery -A app.workers.celery_app:celery_app worker `
  --loglevel=info `
  --pool=solo `
  -Q ml_shadow `
  -n recoverai-ml@%h
```

Windows uses the Celery `solo` pool for local execution.

### 8. Configure the frontend

```powershell
cd frontend

npm install
```

Create `frontend/.env`:

```dotenv
VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1
VITE_TENANT_ID=11111111-1111-1111-1111-111111111111
```

### 9. Start the frontend

```powershell
npm run dev
```

Open:

```text
http://localhost:5173
```

---

## Health checks

### Backend

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/v1/health" |
ConvertTo-Json -Depth 5
```

Expected:

- status `ok`;
- database available;
- Redis available;
- Razorpay mode `test`.

### Frontend

```powershell
$response = Invoke-WebRequest `
  -Uri "http://localhost:5173" `
  -UseBasicParsing

$response.StatusCode
```

Expected:

```text
200
```

### Docker

```powershell
docker compose ps
```

PostgreSQL and Redis should show `healthy`.

---

## Live demo

1. Open the Live Demo dashboard.
2. Enable `Follow newest`.
3. Create a provider-generated Razorpay Test Checkout order.
4. Open Razorpay Checkout.
5. Intentionally fail the Test Mode payment.
6. Refresh provider evidence.
7. Observe the new Recovery Case.
8. Inspect production, AI shadow and ML shadow decisions.
9. Observe an uncertain case entering `HUMAN_REVIEW`.
10. Select `Send payment link`.
11. Enter reviewer identity and reasoning.
12. Approve the action.
13. Wait for Celery execution.
14. Receive the Razorpay Test Payment Link email.
15. Complete the Test Mode payment.
16. Wait for reconciliation.
17. Refresh the dashboard.
18. Observe `RECOVERED` and the complete audit trail.

---

## API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/v1/health` | Service health |
| POST | `/api/v1/cases` | Create a Recovery Case |
| GET | `/api/v1/cases` | List Recovery Cases |
| GET | `/api/v1/cases/{case_id}` | Get one Recovery Case |
| POST | `/api/v1/webhooks/razorpay/{tenant_id}` | Receive Razorpay webhook |
| POST | `/api/v1/cases/{case_id}/evaluate` | Evaluate recovery policy |
| GET | `/api/v1/cases/{case_id}/decisions` | List production decisions |
| POST | `/api/v1/cases/{case_id}/human-review/resolve` | Resolve Human Review |
| GET | `/api/v1/cases/{case_id}/human-reviews` | List Human Reviews |
| GET | `/api/v1/payment-events` | List payment events |
| GET | `/api/v1/ai-shadow/summary` | AI shadow summary |
| GET | `/api/v1/ai-shadow/decisions` | AI shadow decisions |
| GET | `/api/v1/ml-shadow/summary` | ML shadow summary |
| GET | `/api/v1/ml-shadow/decisions` | ML shadow decisions |
| GET | `/api/v1/cases/{case_id}/timeline` | Case audit timeline |
| POST | `/api/v1/test-checkout/orders` | Create Test Order |
| GET | `/api/v1/test-checkout/orders` | List Test Orders |
| POST | `/api/v1/test-checkout/orders/{provider_order_id}/reconcile` | Reconcile Test Order |

Interactive API documentation:

```text
http://127.0.0.1:8000/docs
```

---

## Safety model

RecoverAI enforces the following boundaries:

1. Razorpay integration is restricted to Test Mode.
2. The backend validates the `rzp_test_` key prefix.
3. Real provider actions require an explicit environment switch.
4. Test Checkout has a configurable maximum amount.
5. AI and ML operate only in shadow mode.
6. The deterministic policy engine retains execution authority.
7. Human Review is required for uncertain or high-risk cases.
8. Operator resolutions are auditable.
9. State-version checks prevent stale approvals.
10. Provider references and paid amounts are verified.
11. API secrets never reach the frontend.
12. Provider responses are reduced to safe snapshots.
13. Duplicate provider events are processed idempotently.
14. Failed and recovered payment identities remain separate.
15. Terminal cases cannot execute additional actions.

---

## Honest prototype boundaries

RecoverAI is a hackathon-grade Razorpay Test Mode prototype.

- It does not support Razorpay Live Mode.
- It does not move real money.
- Local Test Checkout can use authenticated server reconciliation when a public webhook URL is unavailable.
- Provider notification acceptance does not prove inbox delivery.
- Automatic retry requires a reusable provider token, mandate or subscription authorization.
- AI recommendations cannot bypass production policy.
- Production authentication, RBAC and deployment hardening remain future work.

---

## Testing

### Backend

```powershell
cd backend

python -m compileall app

pytest

pytest --cov=app --cov-report=term-missing
```

### Frontend

```powershell
cd frontend

npm run build

npm run lint
```

### Git validation

```powershell
git diff --check
```

---

## Design decisions

### Why rules remain in control

Payment recovery affects customers and revenue. Production decisions must remain bounded, deterministic and explainable.

### Why AI and ML use shadow mode

Shadow evaluation allows models to be measured without allowing uncontrolled payment execution.

### Why two payment IDs are stored

A recovered case contains two different financial events:

```text
Original payment → failed
Recovery payment → captured
```

Keeping both IDs preserves financial provenance.

### Why Human Review creates a new decision

The policy escalation remains immutable. Human approval creates a linked decision containing:

- reviewer identity;
- selected action;
- reason;
- source decision;
- resulting decision;
- state version before review;
- state version after review.

---

## Future roadmap

- Public deployment with signed webhook-first processing
- Merchant authentication and RBAC
- Multi-tenant policy configuration
- Provider-agnostic payment adapters
- Mandate and subscription retry support
- Customer communication preferences
- Retry budgets and fatigue controls
- Operational monitoring and alerts
- Model monitoring and drift detection
- Recovery cohort analytics

---

## Why RecoverAI

RecoverAI is more than a retry scheduler.

It combines:

- real provider evidence;
- deterministic economic decisioning;
- policy safety;
- measurable AI and ML assistance;
- human operational control;
- provider-backed customer recovery;
- exact payment reconciliation;
- end-to-end auditability.

The result is a recovery platform designed to increase recovered revenue without sacrificing customer trust or operational control.

---

## Author

**Samradh Dubey**

B.Tech Computer Science and Engineering — Artificial Intelligence & Machine Learning

GitHub: [samradh1718](https://github.com/samradh1718)

---

## Disclaimer

RecoverAI is an educational and hackathon prototype built with Razorpay Test Mode. It is not intended for real customer payments without additional security, compliance, authentication, monitoring and production-readiness work.
