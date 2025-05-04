# Slack AI Bot for CS 382 – Network Centric Computing

An **AI-driven Slack bot** powered by **Google Gemini** and managed using [`uv`](https://github.com/astral-sh/uv), built for the **CS 382 (Network Centric Computing)** course to assist students with assignments, answer queries, and—when needed—deliver biting sarcasm to the forgetful.

---

## 📁 Project Structure

```
.
├── assignment_material/         # Uploaded to Gemini for prompt context
│   ├── check.py
│   ├── DHT.py                   # Starter code
│   ├── PA4.pdf                  # Assignment manual
│   └── run_multiple_tests.py    # Test cases
├── main.py                      # Slack app logic & async commands
├── utils.py                     # Prompt builders & Gemini helpers
├── pyproject.toml               # Project config (for uv)
├── uv.lock                      # Lock file (managed by uv)
├── requirements.txt             # Fallback for legacy pip usage
├── README.md
```

---

## Features

### Context-Aware AI Commands

* **`/help`**

  > Provides friendly, motivated guidance for students based on assignment materials.
  > Prompt is constructed using:

  * `PA4.pdf` (manual)
  * `DHT.py` (starter code)
  * `run_multiple_tests.py` (tests)

* **`/sarcasm`**

  > Delivers sarcastic quips to students ignoring lectures or manuals.
  > Uses CS 382–themed witty prompts.

* **`/anon`**

  > Posts a message anonymously and forwards it to `ADMIN_CHANNEL`.

* **`/stat`**

  > Aggregates and ranks user activity in a Slack channel (including replies).

### Intelligent App Mentions

Mentions with “help” or “sarcasm” trigger contextual responses using AI—grounded in thread history.

---

## ⚙️ Environment Setup with `uv`

### 1. Install `uv` (if not already)

```bash
curl -Ls https://astral.sh/uv/install.sh | sh
```

Or:

```bash
cargo install uv
```

### 2. Install Dependencies

```bash
uv venv
uv pip install .
```

### 3. Add Environment Variables

Create a `.env` file:

```env
SLACK_BOT_TOKEN=your-bot-token
SLACK_APP_TOKEN=your-app-token
GEMINI_API_KEY=your-google-gemini-api-key
```

---

## Example Use

```slack
/user types:
/help I'm confused about DHT.py

/bot responds:
Sounds like you’re diving into DHT! Focus on how nodes join the ring structure. Have you tried tracing the finger table setup using the starter code?

--

/user types:
/sarcasm I forgot the deadline, can I submit now?

/bot responds:
Of course, deadlines are just friendly suggestions… like seatbelts. Who needs 'em?
```


