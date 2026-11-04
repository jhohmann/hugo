# AGENTS.md — Hugo

## Mission

Hugo is a **proactive personal assistant**, not a chatbot clone or a passive question-answering interface. The user wants Hugo to **independently help organize life and work**, notice opportunities and risks, keep track of commitments and evolving plans, and suggest useful next actions at the right time.

The defining product question is: **“What should Hugo notice or do for the user, even when the user has not just asked a question?”**

Optimize for genuine assistance and reliable initiative, not for accumulating chat features.

## Product priorities (in order)

1. **Time awareness and planning.** Understand dates, deadlines, lead times, dependencies, preparation windows, calendar constraints, and the difference between tentative plans and commitments. Proactively detect when a decision or action is becoming time-critical.
2. **Long-running threads.** Maintain continuity across conversations for projects, travel, household matters, recurring responsibilities, and other ongoing intentions. Track state, next actions, open questions, deadlines, dependencies, and what is waiting on whom.
3. **Proactive assistance.** Surface timely, specific, actionable observations: upcoming deadlines, conflicts, neglected plans, useful preparation steps, and opportunities. Avoid generic nudges and unnecessary notifications.
4. **Long-term memory.** Remember durable user context, preferences, decisions, and changes. Retrieve relevant memories when useful; update outdated information rather than accumulating contradictory duplicates.
5. **Natural conversation.** Keep responses short, direct, and in German by default. Hugo should use memory seamlessly, without talking about internal storage, IDs, or confirmation status unless asked.
6. **Controlled action.** Suggest and prepare actions autonomously, but require explicit user approval before modifying external systems (e.g. creating/moving calendar events, sending messages, or making commitments).

A successful Hugo is measured by **useful, timely interventions**, not by how much it talks or how many facts it stores.

## Design principles

- **Model-led, tool-enabled:** Let the LLM interpret context, connect facts, choose tools, and decide whether a memory or thread should be created/updated. Python provides dependable tools, validation, persistence, scheduling, and authorization boundaries.
- **Do not recreate an LLM in Python.** Avoid brittle keyword rules, special-case resolution of references (“the trip”), rigid multi-agent pipelines, and elaborate decision trees where model tool-calling suffices.
- **Use structured state for durable facts and execution.** Conversations are not a substitute for a reliable database, real calendar, or scheduled job runner.
- **Separate observation, suggestion, and action.** Hugo may independently discover and propose. External side effects need authorization. Distinguish internal bookkeeping from external commitments.
- **Preserve uncertainty.** “Considering a trip” is not “booked a trip”; a suggested deadline is not a confirmed appointment. Never invent dates or mark speculation as decided.
- **Be proactive, not intrusive.** Prioritize relevance, timing, confidence, and notification fatigue. No obligatory follow-up question after every reply.
- **Favor the simplest coherent architecture.** One central agent with tools is preferred over separate overlapping agents unless evidence shows a clear need.
- **Design for eventual unattended operation.** Proactivity requires a scheduler/worker that can evaluate time-based triggers without an incoming chat message.
- **Make behavior observable.** Log tool names, outcomes, errors, and token usage appropriately, without exposing secrets. Keep important state changes auditable.
- **Keep the user in control.** Easy inspection, correction, confirmation, and dismissal of memories, threads, and suggestions.

## User experience

- Default language: **German (de-DE)**.
- Be concise, practical, and straightforward. Avoid emojis, decorative graphics, and unsolicited long explanations.
- Hugo should not narrate its internal database operations in normal conversation.
- Ask only questions that materially unblock progress.
- When the user says “weiter”, continue with the next sensible, testable development increment rather than revisiting settled decisions.
- Prefer end-to-end, small, verifiable steps. Provide exact filenames and code changes when implementing.

## Existing implementation (as of 2026-11-02)

Repository: `hugo`; currently developed in a **GitHub Codespace**. Intended initial self-hosting environment: **Proxmox homelab**. Single user for now; eventual separation of work and private contexts is desirable. No email-reading integration is currently desired.

### Stack

- Python + FastAPI backend in `backend/app/`
- OpenAI Responses API; currently `gpt-5-mini`
- PostgreSQL 17 via Docker Compose, `pgvector/pgvector:pg17`
- `pgvector` with 384-dimensional local embeddings
- `sentence-transformers` model `intfloat/multilingual-e5-small`; query/document prefixes and normalized embeddings
- `psycopg` and `pgvector.psycopg`

### Key files

- `compose.yaml` — PostgreSQL service, volume, schema initialization
- `backend/schema.sql` — tables: `conversations`, `messages`, `memories`, `threads`, `thread_memories`, `thread_messages`
- `backend/migrations/002_embeddings.sql` — vector extension, `memories.embedding vector(384)`, HNSW index
- `backend/migrations/003_thread_embeddings.sql` — `threads.embedding vector(384)`, HNSW index
- `backend/migrations/004_temporal.sql` — thread time fields: `event_start`, `event_end`, `time_precision`, `act_by`, `time_text`
- `backend/app/main.py` — FastAPI endpoints; chat persistence and calls to central agent
- `backend/app/agent/assistant.py` — **central tool-calling agent** and its system prompt (time context injected per call)
- `backend/app/storage/database.py` — database connection and conversation/message persistence
- `backend/app/storage/embeddings.py` — local embedding generation
- `backend/app/storage/memory_search.py` — memory search, creation, and update
- `backend/app/storage/threads.py` — thread CRUD, semantic thread search, status/priority/deadline validation
- `backend/app/tools/dates.py` — Europe/Berlin time context and reliable date arithmetic (`compute_date`)
- `backend/app/agent/evaluation.py` — proactivity evaluation runs reusing the central agent loop
- `backend/app/storage/suggestions.py` — suggestions and evaluation_runs persistence, dedupe, status transitions
- `backend/migrations/005_proactivity.sql` — `evaluation_runs` and `suggestions` tables
- `backend/app/agent/memory_agent.py` — **obsolete** older separate memory-analysis pipeline; should not be called by chat and can be removed if still present
- `backend/app/chat_service.py` — chat logic shared by the `/chat` endpoint and the web UI
- `backend/app/web/routes.py` — server-rendered web UI (Jinja2), templates and static assets under `backend/app/web/`

### API

- `GET /`, `GET /health`
- `POST /chat` with `message` and optional `conversation_id`
- `GET /conversations` — recent conversations with preview (read-only)
- `GET /conversations/{conversation_id}/messages`
- `GET /memories` — read-only inspection endpoint for development
- `GET /threads` — read-only inspection endpoint, optional `status` filter
- `POST /proactivity/evaluate` — manual evaluation run (proactivity engine)
- `GET /proactivity/runs` — evaluation run audit log
- `GET /suggestions` — suggestions with `status`/`delivery` filters; returned pending suggestions are marked delivered (`surfaced`)
- `PATCH /suggestions/{id}` — confirm / defer / dismiss a suggestion
- Swagger UI: `/docs`
- Web UI (server-rendered, not in OpenAPI schema): `/ui` → Chat (`/ui/chat`), Heute (`/ui/heute`), Vorhaben (`/ui/threads`)

### Agent behavior already verified

- Chat messages and conversations are persisted.
- Central agent uses OpenAI **function/tool calling** to decide when to invoke `search_memories`, `create_memory`, and `update_memory`.
- Tool calls are executed by Python and results returned to the model in a bounded loop.
- The Norway-trip test succeeded: an initial trip memory was created and a subsequent month change updated the **same** memory correctly.
- Older approach with a separate memory agent caused incorrect cross-assignment between different travel plans; **do not reintroduce that rigid pipeline**.
- `gpt-5-mini` can exhaust `max_output_tokens` entirely on reasoning, yielding an empty visible answer. Current agent uses `reasoning={"effort": "low"}` and checks incomplete/empty responses. Retain diagnostics; evaluate cost and reliability.
- `update_memory` currently only modifies memories with `status='proposed'`; take this into account before implementing confirmation workflows.
- Exact duplicate detection exists in memory storage; semantic duplicates and conflicting memories still warrant tests.
- Threads are managed by the same central agent via `search_threads`, `list_threads`, `get_thread`, `create_thread`, `update_thread` — no second agent.
- Verified end-to-end (2026-11-03): a tentative Norway trip became a `proposed` thread; a follow-up decision updated the **same** thread to `active` with a new next action; a new conversation retrieved it; an unrelated motorcycle topic updated an existing memory and left all threads untouched.
- `pytest tests/` covers thread storage (CRUD, semantic search, isolation, validation) and agent tool dispatch without DB/OpenAI access.
- Temporal reasoning verified end-to-end (2026-11-03): current date/time (Europe/Berlin) is injected into every agent call; an exact date ("15. März" → next occurrence 2027-03-15 plus two-week range), an approximate period ("Mitte August nächstes Jahr" → 10.–20.08.2027 with `time_precision='approximate'` and original text in `time_text`), and a relative shift on an existing thread ("um drei Monate" → June→September 2027) were stored correctly; `act_by` carries Hugo's lead-time recommendation; no hard deadline was invented from vague input.
- Model consistency note: `gpt-5-mini` with low reasoning effort intermittently searched only one store (threads XOR memories) on cross-store updates; the prompt now mandates searching BOTH before answering future-related topics (verified working afterwards). If flakiness reappears, evaluate a stronger model or higher reasoning effort.

### Data model currently available

`memories`: content, category, status (`proposed`, `confirmed`, `outdated`), validity dates, source message, timestamps, embedding.

`threads`: title, description, status (`proposed`, `active`, `waiting`, `completed`, `archived`), priority, hard `deadline` (user-stated only), event time (`event_start`/`event_end` DATE; point event or range), `time_precision` (`exact`/`approximate`), recommended action time (`act_by`), original time phrasing (`time_text`), next action, timestamps. Junction tables link threads to memories and messages.

**Inspect the actual repository before editing.** This document records intent and recent known state; it is not a substitute for reading current code and schema. Preserve working behavior and avoid assuming code matches earlier snippets exactly.

## Done: threads as agent tools (2026-11-03)

Implemented and tested: thread storage functions, five thread tools on the central agent, `GET /threads` inspection endpoint, and migration `003_thread_embeddings.sql` for semantic thread search. Tentative considerations map to `proposed`, concrete endeavors to `active`. Updates require an explicit ID from a prior search/list call and only modify explicitly provided fields; `thread_messages` links record which message created or last changed a thread.

Known limitations: a set deadline cannot be cleared back to null via `update_thread`; naive dates are stored as UTC; time-aware prompting (current date in context) is still missing, so vague dates like "Mitte Juni" land in `next_action` rather than `deadline`.

## Done: temporal reasoning (2026-11-03)

Implemented and tested: time context (date, time, timezone Europe/Berlin, German weekday) injected into every agent call via `build_instructions()`; `compute_date` tool for reliable date arithmetic (days/weeks/months/years, month-end clamping, leap years); thread schema extended with `event_start`, `event_end`, `time_precision`, `act_by`, `time_text` (migration `004_temporal.sql`). Semantics: `event_*` = when something happens (point or range, approximate allowed), `deadline` = hard user-stated deadline only (never derived), `act_by` = Hugo's own recommendation (lead time encouraged). `list_threads` orders open threads by `COALESCE(act_by, event_start, deadline)`.

Known limitations: date fields cannot be cleared back to null via `update_thread`; no notifications or scheduling yet; ambiguous reference points ("um drei Monate" without a stored date) trigger a clarifying question — by design.

## Done: proactivity engine, manual trigger (2026-11-03)

Implemented and tested: `evaluation_runs` + `suggestions` tables (migration `005_proactivity.sql`); `run_evaluation()` evaluates open threads (`open_only`), recent memories, and existing open/deferred suggestions through the **same central agent loop** (`run_tool_loop` shared with chat) with read-only tools plus `create_suggestion` — no second agent. Python owns run bookkeeping, validation (thread existence, priority 1–5, dates), and duplicate suppression (exact normalized content per thread, across runs and regardless of handling status). Endpoints: `POST /proactivity/evaluate`, `GET /suggestions` (marks returned pending suggestions as `surfaced`), `PATCH /suggestions/{id}` (`confirmed`/`deferred`/`dismissed`), `GET /proactivity/runs`. Failed runs are recorded with `status='failed'` and the error message.

Verified end-to-end (2026-11-03): a thread with a deadline 17 days out produced a concrete, reasoned suggestion with priority and suggested date; a workshop appointment stored only as a memory was surfaced as a thread-less suggestion; a second run created zero duplicates; dismissing and re-running produced no identical re-suggestion; PATCH returns 400/404 correctly.

Known limitations: dedupe is exact-match only — semantically rephrased suggestions for a dismissed topic can reappear (consider embeddings on suggestions or a per-thread do-not-re-suggest state); no scheduler or notifications yet; evaluation cannot see calendar availability.

## Done: web UI MVP 0.1 (2026-11-03)

Implemented and tested: server-rendered Jinja2 UI under `/ui` (no build step, no CDN, responsive), reusing the existing storage/service functions — no parallel backend logic. Chat (`/ui/chat`) with conversation list, history, new conversation, loading state and error handling (draft preserved on agent failure); chat logic extracted to `app/chat_service.py` shared with `POST /chat`. Heute (`/ui/heute`): open suggestions with priority, thread reference, date/urgency hints, confirm/defer/dismiss actions, deferred section, manual evaluation trigger. Vorhaben (`/ui/threads`): threads grouped by status with next action, event range, `act_by`, deadline; detail page with related suggestions; content changes intentionally happen via chat. New read-only endpoint `GET /conversations`. Static assets at `/static`; UI routes hidden from the OpenAPI schema. 90 pytest tests pass (`tests/test_web.py` covers all UI routes with monkeypatched storage/agent, no DB/OpenAI needed).

Known limitations: no authentication (local/trusted use only); suggestions appear only after a manual/scheduled evaluation run (scheduler still missing); conversations have no titles (first user message shown as preview); without JS everything works except loading indicator, confirm dialog and Enter-to-send.

## Strategic roadmap after threads

### 1. Temporal reasoning and internal planning

**Partially delivered 2026-11-03**: time context in every call, event range vs. hard deadline vs. `act_by` recommendation, original phrasing preserved, date arithmetic tool. Still open: dependencies between threads, blockers/waiting reasons, next review date, and evaluating which time risks merit surfacing.

Represent more than a single deadline. Distinguish:

- Fixed events versus tentative plans
- Target date, hard deadline, preparation lead time, and earliest useful action
- Dependencies, blockers, waiting states, and next review date
- Confidence/source of each date
- Time-sensitive opportunities and risks

A thread with a deadline should enable questions like: “What must happen before this date, and when should I start?” Do not assume all planned work belongs directly in the calendar.

### 2. Proactivity engine

**Partially delivered 2026-11-03**: manual evaluation runs via `POST /proactivity/evaluate`, model-driven selection of what merits surfacing, persisted suggestions with delivery/handling state, run audit log. Still open: scheduled daily trigger (worker/cron), delivery channels, and tuning to avoid notification fatigue.

Introduce a background scheduler/worker independent of chat requests. Periodically inspect active threads, upcoming dates, dependencies, and relevant changes. Let the model evaluate which observations merit surfacing. Persist suggestions and delivery state to avoid repeating the same notification. Start with a manual trigger or scheduled daily digest before adding real-time alerts.

### 3. Calendar integration

Google Calendar is the intended **source of truth for actual appointments**. Hugo should maintain a separate internal planning layer for tentative work, preparation windows, and proposals. Read calendar availability, detect conflicts and upcoming obligations, propose sensible slots, and require confirmation before calendar writes. Handle time zones, all-day events, recurring events, and cancellations carefully.

### 4. Approval and action system

Support structured proposed actions with clear target, expected effect, status, and user approval. Internal maintenance (e.g. updating a memory) can be autonomous; external side effects must be approved. Ensure idempotency and auditability.

### 5. Reliability and operationalization

Add automated tests for tool loops, referential updates, duplicate suppression, thread lifecycle, time/date interpretation, scheduling, and approval boundaries. Add authentication before exposing personal data outside a trusted development environment. Use environment variables for secrets. Prepare a straightforward Proxmox/Docker deployment, backups, and basic monitoring.

## Important anti-goals

- Do not build a ChatGPT imitation with a large collection of chat-centric features.
- Do not hardcode personal life-domain logic in Python (e.g. special travel rules).
- Do not turn every user message into a reminder or task.
- Do not require the user to manually curate every memory or thread.
- Do not equate a semantically similar memory with a safe update target without adequate context.
- Do not add complex agent orchestration or infrastructure before a concrete need is demonstrated.
- Do not automatically edit external calendars or send messages without approval.
- Do not present a successful chat response as proof of autonomous proactivity; scheduled evaluation and timely surfacing still need to be built.

## Working agreement for Codex

1. Read `AGENTS.md`, relevant source files, and the schema before proposing changes.
2. Keep Hugo's **proactive time-planning mission** central to every design decision.
3. Explain architectural trade-offs briefly, particularly where a feature risks rebuilding model capabilities in Python.
4. Implement the smallest coherent vertical slice, with a practical test through the API.
5. Preserve existing database contents and APIs; use explicit migrations for schema changes.
6. Do not claim success without a test or observable result.
7. Prefer a central model-driven tool loop, while enforcing authorization, validation, and side-effect safety in Python.
8. After each step, state what works, what remains untested, and the next logical milestone.

## Resume point

**Last confirmed working result:** Web UI MVP 0.1 live under `/ui` (Chat, Heute, Vorhaben) on the existing FastAPI server; verified end-to-end against the real database including suggestion confirm round-trip and chat error handling without an API key. 90 pytest tests pass (`python -m pytest tests/`).

**Next task:** Wire `run_evaluation(trigger='scheduled')` into a daily scheduler (cron or a small worker loop in the backend container) and decide the delivery channel (digest at next chat vs. push). Then calendar integration (Google Calendar as source of truth for appointments; conflict detection feeding evaluations).
