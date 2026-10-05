# GenAI Studio — Generative AI Content & Image Pipeline Platform

Backend-only **FastAPI** service for **text**, **image**, and **code** generation with **versioned prompt templates**, **style presets**, **LLM-based moderation**, **A/B prompt testing**, **usage quotas**, **cost/token analytics**, and **Celery** background jobs. Designed as a **portfolio-grade** example of generative AI engineering, prompt tooling, and multi-provider integration.

**Latest:** Content crew (`POST /api/crews/content`) — writer → editor → critic with Celery worker `genai.run_content_crew`.

**Secrets** live in environment variables only (see `.env.example`). No API keys are hardcoded.

---

## Architecture (ASCII)

```
Templates + Style Presets
         |
         v
 +-------+--------+---------+
 | Text    Image    Code    |
 | Generator Generator Generator |
 +-------+--------+---------+
         |
         v
   Content Moderator
         |
         v
    Output Store (DB + disk)
         |
         v
   Prompt Optimizer  ----->  A/B Testing  ----->  Version Management
```

---

## Generation types

| Type | Capabilities | Providers / models (configurable) |
|------|----------------|-------------------------------------|
| **Text** | Blog posts, marketing copy, product descriptions, email, social hints; templates; streaming (SSE); structured JSON | OpenAI Chat (`LLM_MODEL`), Anthropic Messages |
| **Image** | DALL·E 3, Stability AI SD3-style endpoint, Replicate | `IMAGE_GEN_PROVIDER`: `openai_dalle` / `stability_ai` / `replicate` |
| **Code** | Generate, review, convert, explain | Same LLM stack as text |

---

## Prompt template system

- **Categories**: `text_gen`, `image_gen`, `code_gen`, `translation`, `summarization`
- **Variables**: `{{variable}}` placeholders in `template_text`
- **Versioning**: `POST /api/templates/{id}/version` creates a new row linked via `parent_version_id`, increments `version`
- **Performance**: `usage_count`, `performance_score`, analytics tie-ins to jobs and optional feedback ratings

---

## Content moderation

- **ContentModerator** classifies prompts and outputs with LLM-assisted JSON: categories `violence`, `sexual`, `hate`, `self_harm`, `illegal` (scores 0–1) and decisions **`allow` / `block` / `review`**
- Toggle with **`CONTENT_MODERATION_ENABLED`**
- Blocked outputs mark jobs as **`blocked`** and avoid shipping unsafe text

---

## A/B testing workflow

1. Create two **PromptTemplate** records.
2. Create **`ABPromptTest`** with `prompt_a_id`, `prompt_b_id`, and `test_input`.
3. **`POST /api/ab-tests/{id}/run`** queues **`ab_test_task`** (Celery): generates both outputs, runs **LLM-as-judge** (`PromptOptimizer.ab_evaluate`), stores `winner` and `auto_eval_scores`.
4. **`GET /api/ab-tests/{id}/results`** returns the latest stored results.

---

## Style presets

- **Categories**: `writing_style`, `image_style`, `tone`
- **Config JSON** may include `system_prompt_modifier`, `style_keywords`, `negative_prompts` (consumed by generators where applicable)
- **`POST /api/styles/{id}/preview`** runs a short LLM generation with the preset applied

---

## Usage quotas & cost tracking

- **`UsageQuota`** per user: daily text/image caps, lifetime tokens and estimated cost
- **`POST /api/generate/*`** increments usage on success
- **Celery Beat** runs **`reset_quotas_task`** at **UTC midnight** (`app/tasks/celery_app.py`)
- **`MAX_BATCH_SIZE`** caps async batch requests

---

## Example requests

**Login**

```http
POST /api/auth/login
Content-Type: application/json

{"email": "you@example.com", "password": "yourpassword"}
```

**Text generation**

```http
POST /api/generate/text
Authorization: Bearer <token>
Content-Type: application/json

{
  "prompt": "Write a 150-word LinkedIn post about responsible AI in healthcare.",
  "content_type": "social",
  "temperature": 0.7
}
```

**Example response (abridged)**

```json
{
  "job_id": 12,
  "text": "...",
  "model_used": "gpt-4o-mini",
  "tokens_used": 420,
  "cost_estimate": 0.0001,
  "generation_time_ms": 1800,
  "moderation": { "output": { "decision": "allow", "categories": { "...": 0.0 } } }
}
```

**Image generation (DALL·E)**

```http
POST /api/generate/image
Authorization: Bearer <token>
Content-Type: application/json

{
  "prompt": "Minimalist product hero shot of a ceramic mug, soft daylight",
  "size": "1024x1024",
  "quality": "hd",
  "count": 1
}
```

---

## API endpoints (summary)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/auth/register` | Register (default role: creator) |
| POST | `/api/auth/login` | JWT access token |
| GET | `/api/auth/me` | Current user |
| POST | `/api/generate/text` | Text generation (prompt or template) |
| POST | `/api/generate/image` | Image generation |
| POST | `/api/generate/code` | Code generation |
| POST | `/api/generate/batch` | Queue Celery batch text jobs |
| POST | `/api/generate/stream` | SSE streaming (OpenAI streaming; Anthropic falls back to single chunk) |
| POST | `/api/generate/structured` | JSON-schema-style structured output |
| POST | `/api/generate/ab-inline` | Quick two-prompt A/B on same input |
| CRUD | `/api/templates` | Prompt templates |
| POST | `/api/templates/{id}/render` | Preview rendered template |
| POST | `/api/templates/{id}/version` | New template version |
| GET | `/api/templates/{id}/versions` | Versions (same name lineage) |
| GET | `/api/templates/{id}/performance` | Aggregated stats |
| CRUD | `/api/collections` | Content collections |
| POST | `/api/collections/{id}/items` | Add job to collection |
| GET | `/api/collections/{id}/export` | Export JSON |
| CRUD | `/api/styles` | Style presets |
| POST | `/api/styles/{id}/preview` | Preview generation |
| CRUD | `/api/ab-tests` | A/B tests |
| POST | `/api/ab-tests/{id}/run` | Queue evaluation |
| GET | `/api/ab-tests/{id}/results` | Results |
| GET | `/api/jobs` | List jobs (scoped to user; admins see all) |
| GET | `/api/jobs/{id}` | Job detail |
| GET | `/api/jobs/{id}/output` | Download image or plain text |
| GET | `/api/analytics/usage` | Counts by period |
| GET | `/api/analytics/costs` | Tokens / estimated cost |
| GET | `/api/analytics/quality` | Avg ratings per template |
| GET | `/api/analytics/popular-templates` | Top templates by usage |

---

## Tech stack

- **FastAPI**, **Pydantic Settings**, **SQLAlchemy 2 async**, **asyncpg**
- **Celery** + **Redis** (broker, results, Beat)
- **OpenAI** & **Anthropic** SDKs for chat / JSON / streaming
- **httpx** for DALL·E / Stability / Replicate image APIs
- **sse-starlette** for SSE streaming
- **JWT** + **passlib[bcrypt]** for auth
- **tiktoken** for token estimation fallbacks
- **Pillow** / **numpy** (image pipeline hooks)

---

## Project structure

```
app/
  main.py                 # FastAPI app, routers, lifespan (creates tables)
  core/                   # config, database, security, deps
  models/                 # User, PromptTemplate, GenerationJob, ...
  schemas/                # Pydantic request/response models
  api/routes/             # auth, generate, templates, collections, ...
  services/
    generators/           # text, image, code
    content_moderator.py
    prompt_optimizer.py
    quota_service.py
    llm_client.py
  tasks/                    # Celery app, generation_tasks, maintenance_tasks
```

---

## Running locally

1. Copy **`.env.example`** → **`.env`** and set **`SECRET_KEY`**, **`LLM_API_KEY`**, **`DATABASE_URL`**, **`REDIS_URL`**, and image keys as needed.
2. `pip install -r requirements.txt`
3. `uvicorn app.main:app --reload`

**Docker**

```bash
docker compose up --build
```

API: `http://localhost:8000` — OpenAPI: `http://localhost:8000/docs`

**Celery** (separate terminals):

```bash
celery -A app.tasks.celery_app.celery_app worker -l INFO
celery -A app.tasks.celery_app.celery_app beat -l INFO
```

---

## Scaling notes

- **API**: horizontal scale behind a load balancer; shared **Postgres** and **Redis**
- **Workers**: add Celery workers for batch, image, and A/B tasks
- **Storage**: move `STORAGE_PATH` to **object storage** (S3/GCS) in production
- **Migrations**: `create_all` is for demos; use **Alembic** for production schema evolution
- **SSE / long requests**: tune reverse-proxy timeouts; consider WebSockets for heavy streaming

## CI/CD

GitHub Actions pipeline: lint → test → Docker build with BuildKit caching.

## Observability

- **Usage Tracking**: Token consumption, cost per generation, quota monitoring
- **Quality Metrics**: User feedback ratings, prompt version performance
- **Structured Logging**: Generation requests with model/latency/cost metadata
- **Alerting**: Quota exhaustion, moderation block rate spikes

## Cloud Deployment

- **AWS Bedrock**: Alternative LLM provider (Claude, Titan) for enterprise
- **AWS S3**: Generated image storage with CloudFront CDN
- **AWS RDS**: PostgreSQL for templates, jobs, analytics
- **GCP Vertex AI**: Alternative image generation (Imagen)
- **Replicate**: Scalable image generation API

---

## License

MIT (adjust for your portfolio).
