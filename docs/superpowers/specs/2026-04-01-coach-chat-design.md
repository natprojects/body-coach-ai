# Coach Chat — Design Spec

**Goal:** Implement a multi-conversation AI coach chat in the Coach tab, covering exercise technique, program modifications, recovery, nutrition, sleep, stress, and motivation.

**Architecture:** New isolated `app/modules/coach/` blueprint with its own models, routes, and system prompt. Frontend has two states: thread list and thread view, rendered inside the existing Coach tab panel.

**Tech Stack:** Flask SSE streaming, SQLAlchemy, Anthropic API (claude-sonnet-4-6 for chat, claude-haiku-4-5-20251001 for title generation), existing `build_base_system()` + new coach context builder.

---

## Data Model

**File:** `app/modules/coach/models.py`

```python
class ChatThread(db.Model):
    __tablename__ = 'chat_threads'
    id            = Integer, primary key
    user_id       = Integer, FK → users.id, not null
    title         = String(200), default='Нова розмова'
    created_at    = DateTime, default utcnow
    updated_at    = DateTime, default utcnow, updated on write

class ChatMessage(db.Model):
    __tablename__ = 'chat_messages'
    id            = Integer, primary key
    thread_id     = Integer, FK → chat_threads.id, not null
    role          = String(20), not null  # 'user' | 'assistant'
    content       = Text, not null
    created_at    = DateTime, default utcnow
```

`ChatThread.updated_at` is refreshed every time a new message is added to that thread. Thread list is sorted by `updated_at` descending.

Title generation: after the first complete user+assistant exchange, a separate `complete()` call with `claude-haiku-4-5-20251001` generates a 4–6 word Ukrainian title from the user's first message. The title is saved via `PATCH /api/coach/threads/<id>`.

---

## Backend

**File:** `app/modules/coach/routes.py`
**Blueprint prefix:** `/api/coach`
**Registered in:** `app/__init__.py`

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/threads` | List all threads for user, sorted by `updated_at` desc. Returns `[{id, title, updated_at}]` |
| POST | `/threads` | Create new thread. Returns `{thread_id}` |
| GET | `/threads/<id>` | Get thread messages (last 100, chronological). Returns `{id, title, messages: [{role, content, created_at}]}` |
| POST | `/threads/<id>/chat` | Send message + stream SSE response. Saves both user and assistant messages. |
| POST | `/threads/<id>/generate-title` | Generate title via haiku from first user message. Returns `{title}`. Called by client after first `[DONE]`. |
| DELETE | `/threads/<id>` | Delete thread and all its messages. |

### Chat endpoint flow (`POST /threads/<id>/chat`)

1. Validate thread belongs to `g.user_id`
2. Save user message to `ChatMessage`
3. Load last 50 messages from this thread as conversation history
4. Build system prompt (see below)
5. Stream response via `get_client().messages.stream()`
6. On completion: save assistant message, update `thread.updated_at`
7. Client detects first exchange (thread had 0 messages before) → calls `POST /threads/<id>/generate-title` → updates title in UI

SSE format: `data: <chunk>\n\n`, terminated with `data: [DONE]\n\n`

### System Prompt — Coach Context

**File:** `app/modules/coach/context.py` — function `build_coach_context(user_id) -> str`

Combines:
1. `build_base_system(user_id)` — user profile + today's check-in
2. Active program: name, periodization type, current week number
3. Last completed workout: date, exercise names, actual sets (weight × reps, RPE)
4. Last 3 pain journal entries: body part, intensity, date

**Coach persona** (prepended to system):

```
You are an elite personal coach combining expertise of:
physical therapist, rehabilitation therapist, biomechanics specialist,
sports nutritionist, registered dietitian, sport psychologist,
exercise psychologist, strength & conditioning coach, wellness coach.

Rules:
- Always respond in the user's language (Ukrainian if app_language='uk')
- Be specific — reference the user's actual data (their program, last workout, check-in)
- Never give generic advice. "Your bench press was 60kg at RPE 8 yesterday — ..."
- Keep responses concise: 3–5 bullet points or short paragraphs
- If asked about pain/injury: always recommend seeing a doctor for diagnosis
- Use markdown headers and bullets (rendered in the app)
```

---

## Frontend

**All changes in:** `app/templates/index.html`

### Coach tab — two view states

Controlled by `S.coachView`: `'list'` | `'thread'`

**List view** (`S.coachView === 'list'`):
- Header: "COACH" title + ✏️ new-thread button (top right)
- If no threads: empty state card — "Запитай свого коача" + "ПОЧАТИ РОЗМОВУ" button
- Thread list: cards sorted by `updated_at`, each showing title + relative date ("2 год тому", "вчора")
- Tap card → load thread and switch to thread view
- Long-press or swipe → show delete button

**Thread view** (`S.coachView === 'thread'`):
- Header: thread title (truncated to 30 chars) + ← back button
- Scrollable messages area (flex-column, newest at bottom)
- User messages: right-aligned, blue background
- Assistant messages: left-aligned, dark card background, markdown rendered
- Streaming: assistant bubble appears immediately with `▌` cursor, text fills in as chunks arrive
- Input area (fixed bottom): auto-resizing `<textarea>` + send button
- Enter → send, Shift+Enter → newline
- Input disabled while streaming

### State

```javascript
S.coachView = 'list'          // 'list' | 'thread'
S.coachThreads = []           // [{id, title, updated_at}]
S.activeThread = null         // {id, title, messages: []}
S.coachStreaming = false       // true while SSE in progress
```

### Key functions

- `loadCoachTab()` — fetch thread list, render
- `openThread(id)` — fetch thread messages, switch to thread view
- `newThread()` — POST /threads, open empty thread view
- `sendCoachMessage()` — POST /threads/<id>/chat, handle SSE stream
- `renderCoachList()` — render thread list HTML
- `renderCoachThread()` — render message bubbles
- `appendCoachChunk(chunk)` — append streamed text to last assistant bubble
- `deleteThread(id)` — DELETE, remove from list

### CSS additions

- `.coach-thread-card` — thread list item
- `.coach-msg-user` — user bubble (right, blue)
- `.coach-msg-ai` — assistant bubble (left, dark)
- `.coach-input-area` — fixed bottom input zone
- `.coach-empty` — empty state

---

## Error Handling

- Network error during stream → show "Помилка з'єднання. Спробуй ще раз." in bubble
- Thread not found (deleted from another device) → redirect to list
- Empty message → ignore send

---

## Out of Scope

- Voice messages
- Image upload (food photos for nutrition)
- Thread search
- Thread renaming by user
- Push notifications
