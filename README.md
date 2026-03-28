# Mimir's Memory Hub

**A local AI chat app where your AI actually remembers you.**

Mimir's Memory Hub runs entirely on your machine. Point it at a local model or a cloud API, and start chatting with an AI that builds a real memory of your conversations — one that persists, evolves, and shapes future responses the way a person's memory does.

No subscriptions. No data leaving your machine (unless you choose a cloud API). No conversation limit. No forgetting.

---

## What Makes It Different

Most AI chat apps give the AI a simple chat history window. Mimir gives it something closer to actual memory:

- **Memories persist between sessions** — the AI remembers things you told it last week
- **Memories carry emotional weight** — important or emotional moments are recalled more readily
- **Memories fade naturally** — less significant things are gradually forgotten, just like a real mind
- **Mood evolves over time** — how the AI feels right now shapes what it remembers and how it responds
- **Multiple characters** — create distinct AI personalities, each with their own separate memory
- **Multi-agent conversations** — get multiple characters talking together in one conversation

---

## Features

| | |
|---|---|
| 💬 **Streaming chat** | Responses appear token-by-token in real time |
| 🧠 **Persistent memory** | Every conversation turn is stored and recalled in future sessions |
| 👤 **Characters** | Create custom AI personas with names, personalities, and backstories |
| 🃏 **SillyTavern import** | Import character cards directly — single files or entire folders |
| 🤝 **Multi-agent chat** | Multiple characters in one conversation, with configurable turn order |
| 📊 **Memory browser** | Search, filter, edit, cherish, pin, or delete individual memories |
| 📈 **Visualizations** | Mood timeline, memory landscape, neurochemistry charts |
| 🔧 **Agent tools** | In agent mode: sandboxed file access, web search, custom tool permissions |
| 🖥️ **Local or cloud** | Ollama, local GGUF files, OpenAI, Anthropic, or Google |

---

## Supported LLM Backends

| Backend | What You Need |
|---|---|
| **Ollama** (recommended) | [Install Ollama](https://ollama.com) and pull any model — free, fully local |
| **Local GGUF** | Any `.gguf` model file on your drive — GPU acceleration supported |
| **OpenAI** | An OpenAI API key (GPT-4o, GPT-4-turbo, etc.) |
| **Anthropic** | An Anthropic API key (Claude Sonnet, Haiku) |
| **Google** | A Google API key (Gemini 2.0 Flash) |

You can switch backends at any time from the Settings page.

---

## Installation

### Requirements
- Python 3.10 or newer
- Git

### Step 1 — Clone the repo

```bash
git clone https://github.com/Kronic90/Mimirs-Memory-Hub.git
cd Mimirs-Memory-Hub
```

### Step 2 — Create a virtual environment

```bash
python -m venv venv
```

Activate it:

**Windows:**
```
venv\Scripts\activate
```

**macOS / Linux:**
```
source venv/bin/activate
```

### Step 3 — Install dependencies

```bash
pip install fastapi uvicorn httpx python-multipart
```

For local GGUF model support (optional):
```bash
pip install llama-cpp-python
```

For agent web search tools (optional):
```bash
pip install duckduckgo-search beautifulsoup4 lxml
```

### Step 4 — Set up a model

**Option A — Ollama (easiest, fully local):**

Download from [ollama.com](https://ollama.com), then pull a model:

```bash
ollama pull mistral
```

Any model from the [Ollama library](https://ollama.com/library) works — `llama3`, `qwen2.5`, `phi4`, `gemma3`, etc.

**Option B — Local GGUF file:**

Drop any `.gguf` model file anywhere on your drive. Mimir will find it automatically when you scan from the Models page.

**Option C — Cloud API:**

Have your API key ready. You'll enter it in the Settings page after launching.

---

## Running Mimir's Memory Hub

```bash
python -m playground
```

This starts the server on **http://127.0.0.1:19009** and opens your browser automatically.

---

## Quick Start Guide

### First launch
1. Go to **Settings** (sidebar)
2. Select your backend (Ollama, Local, OpenAI, etc.)
3. Enter your API key if using a cloud backend
4. Set a persona name — this is what the AI calls itself

### Start chatting
1. Go to **Chat** (sidebar)
2. Select a **Preset** — try *Companion* for a friendly conversational AI, or *Agent* for a task-focused assistant
3. Type and press `Enter`

The AI will remember your conversations automatically. Each time you return, it recalls relevant things from past sessions to inform its responses.

### Create a character
1. Go to **Characters** (sidebar)
2. Click **New Character**
3. Fill in the name, personality description, and an opening greeting
4. Select the character from the Chat page to start a conversation with it

Each character has completely separate memory — their experiences don't bleed into each other.

### Import SillyTavern characters
1. Go to **Characters** → **Bulk Import**
2. Enter the path to your SillyTavern `Characters` folder
3. Click Import — all characters come in with full metadata preserved

### Multi-agent conversations
1. Go to **Multi-Chat** (sidebar)
2. Click **New Conversation** and give it a title
3. Click **+ Add Agent** to add characters
4. Use the ⚙️ gear button to set turn order:
   - **Address by Name** — only agents you mention by name respond
   - **Sequential** — agents take turns one at a time, round-robin
   - **All Respond** — every agent responds each round

### Browse and manage memory
1. Go to **Memory** (sidebar)
2. **Browse** — scroll through all stored memories, filter by emotion or source
3. **Search** — find memories by topic using semantic search
4. Click any memory to **Edit**, **Cherish** (protect from forgetting), **Pin** (permanent), or **Delete**

### Download models
1. Go to **Models** (sidebar)
2. **Ollama tab** — pull models by name (e.g. `mistral`, `llama3.2`)
3. **HuggingFace tab** — search for GGUF models, browse files, and download with a progress bar
4. **Local tab** — scan your drives to discover GGUF files you already have

---

## Data Storage

All your data is stored locally in `playground_data/` (created automatically on first run):

```
playground_data/
├── settings.json          ← Your settings (backend, model, API keys)
├── profiles/
│   └── default/
│       └── mimir_data/    ← Your AI's memory database
├── characters/            ← Character files
├── conversations/         ← Multi-agent conversation history
└── models/                ← Downloaded GGUF models (if any)
```

Nothing is synced anywhere. API keys are stored only in `settings.json` on your machine.

---

## The Memory Presets

| Preset | Best for | Memory style |
|---|---|---|
| **Companion** | Friendly, emotional conversations | High emotion weight, relationship-focused |
| **Character** | Roleplay and immersive fiction | Maximum emotion weight, fully in-character |
| **Agent** | Tasks, research, file work | Low emotion weight, tool-use enabled |
| **Assistant** | General help and Q&A | Minimal emotional processing, practical |
| **Custom** | Whatever you want | Fully configurable |

---

## Tips

- **Cherish** important memories so they never decay — use the 💎 button in the Memory browser
- **Anchor** critical facts so they always surface — use the ⚓ button
- Run **Sleep** (Memory → Sleep) to consolidate and tidy the memory database, same as how human sleep consolidates the day
- Each **profile** is a completely separate memory space — useful for keeping different contexts isolated
- In **Agent mode**, configure tool permissions to let the AI read files or search the web on your behalf

---

## Presets in Agent Mode

When using the **Agent** preset, Mimir can use sandboxed tools:

- **File read/write** — within whitelisted directories only
- **Web search** — DuckDuckGo, top results only
- **Fetch page** — retrieve and strip HTML from URLs

Configure which tools are enabled and which paths/domains are allowed under **Tools** in the sidebar.

---

## License

Private repository. All rights reserved.
