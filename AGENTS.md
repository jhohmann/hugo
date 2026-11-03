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
- `backend/app/main.py` — FastAPI endpoints; chat persistence and calls to central agent
- `backend/app/agent/assistant.py` — **central tool-calling agent** and its system prompt
- `backend/app/storage/database.py` — database connection and conversation/message persistence
- `backend/app/storage/embeddings.py` — local embedding generation
- `backend/app/storage/memory_search.py` — memory search, creation, and update
- `backend/app/agent/memory_agent.py` — **obsolete** older separate memory-analysis pipeline; should not be called by chat and can be removed if still present

### API

- `GET /`, `GET /health`
- `POST /chat` with `message` and optional `conversation_id`
- `GET /conversations/{conversation_id}/messages`
- `GET /memories` — read-only inspection endpoint for development
- Swagger UI: `/docs`

### Agent behavior already verified

- Chat messages and conversations are persisted.
- Central agent uses OpenAI **function/tool calling** to decide when to invoke `search_memories`, `create_memory`, and `update_memory`.
- Tool calls are executed by Python and results returned to the model in a bounded loop.
- The Norway-trip test succeeded: an initial trip memory was created and a subsequent month change updated the **same** memory correctly.
- Older approach with a separate memory agent caused incorrect cross-assignment between different travel plans; **do not reintroduce that rigid pipeline**.
- `gpt-5-mini` can exhaust `max_output_tokens` entirely on reasoning, yielding an empty visible answer. Current agent uses `reasoning={"effort": "low"}` and checks incomplete/empty responses. Retain diagnostics; evaluate cost and reliability.
- `update_memory` currently only modifies memories with `status='proposed'`; take this into account before implementing confirmation workflows.
- Exact duplicate detection exists in memory storage; semantic duplicates and conflicting memories still warrant tests.

### Data model currently available

`memories`: content, category, status (`proposed`, `confirmed`, `outdated`), validity dates, source message, timestamps, embedding.

`threads`: title, description, status (`proposed`, `active`, `waiting`, `completed`, `archived`), priority, deadline, next action, timestamps. Junction tables link threads to memories and messages.

**Inspect the actual repository before editing.** This document records intent and recent known state; it is not a substitute for reading current code and schema. Preserve working behavior and avoid assuming code matches earlier snippets exactly.

## Immediate next step: threads as agent tools

The next development increment is to expose the existing `threads` table to the **same central agent**, not to create a second agent.

Suggested tools:

- `search_threads` — retrieve relevant open/archived threads; consider both semantic and structured filters as appropriate
- `create_thread` — create a persistent ongoing initiative
- `update_thread` — change status, deadline, next action, or description without losing context
- `get_thread` / `list_threads` — inspect a specific thread or active portfolio, as useful

Add a read-only `GET /threads` endpoint for testing. Prefer clear tool schemas, safe validation, and small changes. Keep memories (facts/decisions) conceptually separate from threads (ongoing initiatives). Avoid creating a thread for every passing remark. Test: create an initiative, change its timing in a follow-up, retrieve it in a new conversation, and confirm that unrelated initiatives remain unchanged.

## Strategic roadmap after threads

### 1. Temporal reasoning and internal planning

Represent more than a single deadline. Distinguish:

- Fixed events versus tentative plans
- Target date, hard deadline, preparation lead time, and earliest useful action
- Dependencies, blockers, waiting states, and next review date
- Confidence/source of each date
- Time-sensitive opportunities and risks

A thread with a deadline should enable questions like: “What must happen before this date, and when should I start?” Do not assume all planned work belongs directly in the calendar.

### 2. Proactivity engine

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

**Last confirmed working result:** The central agent correctly updated an existing Norway travel memory when the user changed the month. The user then stopped for the day and requested this file to continue seamlessly with Codex.

**Next task:** Inspect current code and implement basic `threads` storage functions, agent tools, and a read-only inspection API. Then start the temporal planning/proactivity layer; this is the core product differentiator.
