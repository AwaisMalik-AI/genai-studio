# GenAI Studio — private reference (recruiter / interview)

> Internal notes for you — not required reading for end users.

## What this project demonstrates

- **Generative AI engineering**: multi-modal generation (text, code, image), provider abstraction, error handling, async I/O.
- **Prompt engineering**: templates with `{{variables}}`, system prompts, style modifiers, prompt enhancement for images, optimization/expansion utilities, LLM-as-judge for A/B.
- **Content pipelines**: moderation gate, job lifecycle (`queued` → `generating` → `moderation_check` / `completed` / `failed` / `blocked`), collections and export, analytics.
- **Multi-provider integration**: OpenAI + Anthropic for LLMs; DALL·E / Stability / Replicate for images (swap via env).

## Elevator pitch (recruiter)

“I built a production-style GenAI backend: users manage versioned prompt templates and style presets, generate text/code/images through a moderated pipeline, run A/B tests with an LLM judge, track quotas and costs, and offload batch work to Celery. Everything is configurable via environment variables—no hardcoded secrets.”

## Interview Q&A (samples)

**Q: Why both OpenAI and Anthropic?**  
A: The codebase switches on `LLM_PROVIDER` so we can compare latency, cost, and quality in different environments without code changes.

**Q: How do you handle unsafe content?**  
A: A dedicated `ContentModerator` prompts the model to emit structured scores per category and an allow/block/review decision; high-risk generations never return as normal completions.

**Q: How does template versioning work?**  
A: New rows reference `parent_version_id` and bump `version`; analytics and A/B link back to specific template IDs so we can measure performance over time.

**Q: Why Celery?**  
A: Batch generation and A/B runs can be long-running; isolating them keeps API latency predictable and allows horizontal scaling of workers.

**Q: How would you harden this for real production?**  
A: Alembic migrations, object storage for binaries, stricter RBAC, rate limiting, idempotency keys for paid generation, secret manager integration, observability (OpenTelemetry), and contract tests against provider sandboxes.
