# Changelog

All notable changes to Mimir's Memory Hub.

---

## v0.1.0 — April 2026

### Core
- **6 behavioral presets**: Companion, Agent, Writer, Assistant, Character, Custom
- **46-emotion memory system** with importance scoring, decay, flashbulb moments, and cherished/anchored protection
- **Hybrid recall**: BM25 keyword + VividEmbed semantic + spreading activation + mood-congruent + Proustian random
- **Neurochemistry simulation**: dopamine, serotonin, oxytocin, norepinephrine, cortisol
- **Memory consolidation** (Sleep): Huginn pattern analysis, Muninn deduplication/pruning, Völva dream synthesis
- **Yggdrasil knowledge graph**: temporal, emotional, and entity-based memory connections

### Presets
- **Companion** — emotionally aware conversational partner
- **Agent** — autonomous tool-using assistant with 21 sandboxed tools
- **Writer** — story collaborator with chapter/character/plot tracking
- **Assistant** — virtual PA with appointment tracking, email drafting, proactive reminders
- **Character** — full roleplay with custom personas, greetings, and scenarios
- **Custom** — bring your own system prompt

### Tools & Integrations
- **21 built-in tools**: file I/O, web search, code execution, HTTP requests, PDF reading, CSV queries, screenshots, clipboard, and more
- **MCP support**: connect external tool servers via Model Context Protocol (stdio + SSE)
- **Configurable search provider**: DuckDuckGo default, or plug in SearXNG / custom JSON endpoint
- **SillyTavern character import**: single files or bulk folder scanning

### LLM Backends
- Ollama (recommended), Local GGUF (GPU accelerated), OpenAI, Anthropic, Google, OpenRouter, vLLM, OpenAI-compatible
- HuggingFace model search & download with progress tracking
- Local GGUF directory scanning and auto-detection
- SafeTensors/HuggingFace Transformers GPU support for non-GGUF models

### UI
- **8 visualizations**: Neural Memory Graph, 3D Constellation, Mood Timeline, Neurochemistry, Cherished Wall, Relationships, Topic Clusters, Memory Attic
- **Multi-agent chat**: multiple characters in one conversation with sequential, address-by-name, or all-respond turn modes
- **Memory browser**: search, filter, edit, cherish, pin, delete individual memories
- **Agent tool execution UI**: live tool activity shown inline in chat
- **Conversation search & sort**: filter by text, sort by date or name
- **Light & dark themes**: toggle in settings
- **Mood-reactive UI**: background colors subtly shift with the AI's emotional state
- **Voice I/O**: Edge TTS + Whisper STT with per-character voice selection
- **Image upload**: vision model support with VL auto-detection + BLIP fallback
- **Connection test**: verify backend connectivity before chatting
- **Token tracking**: per-message token count displayed in chat
- **Memory import**: import from any format (JSON, text, markdown) with AI-powered enrichment

### Data & Privacy
- Fully local storage — all data stays in `playground_data/`
- No API keys shipped or stored in builds
- Sandboxed tool execution with explicit user permissions
- Portable Windows build — unzip and run, no Python needed
