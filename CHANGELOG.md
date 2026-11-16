# Changelog

All notable changes to Mimir's Memory Hub.

---

## v1.0.5 — November 2026

New additions:
- **Starter models**: one click downloads and sets up Google's Gemma 4 (E2B or E4B, 4–6 GB) — text, images and voice, running on an ordinary laptop CPU
- **Voice messages**: hold the mic (or attach an audio file); models that can hear (Gemma 4) take in your actual voice, others get a Whisper transcript
- **Character sheets**: picture (click or drop), nicknames, tagline, appearance, traits with suggestions and 🎲 Surprise me, how they talk, likes/dislikes, quirks, backstory, situation, relationship, extra greetings, example dialogue, what they call you, a per-character persona, voice preview, a completeness meter and a "what the AI sees" preview
- **Your persona**: tell every character who you are, once, in Settings
- **Swipes, regenerate & edit**: flip between alternative replies — memories from a discarded reply are undone — and edit any message
- **Greetings**: new chats open with the character's own first message (picked from its greetings)
- **Character cards**: SillyTavern / Chub / TavernAI PNG and JSON cards now import properly, pictures included
- **Character.ai import**: bring a character and its chat history over (CAI Tools exports); chats land in Saved Chats and the moments that mattered become dated memories
- **In-app updates & data import**: update from Settings without losing anything, and bring memories/characters over from an older copy
- **Image previews** on visual memories in the memory graph, and recalled images shown inside the reply
- Small-screen / touch layout

Bug fixes & improvements:
- Images were swapped for a (often nonsense) BLIP caption with Gemma and other local models whose filenames don't say "vision"; a model's vision file now decides
- Claude (Anthropic) and Gemini (Google) failed on every chat message; both now work, with images
- A character's own model now uses its own vision file (a mismatched pair failed with "Failed to load mtmd context"), with a clear message if a pair doesn't match
- Gemma 4's thinking markers no longer leak into replies
- Your real name and "User" are now always the same person in memory (existing memories merge)
- After updating, old feelings no longer all soften at once — the first catch-up is capped at a month
- Group chats keep up to two local models loaded (when RAM allows) instead of reloading every turn
- Different pictures described alike no longer merge into one memory; WebP and other formats no longer fail with "Failed to create bitmap"
- Group chat markdown and memory strips were silently disabled
- llama.cpp backend updated (0.3.36) for Gemma 4 and audio input; the GPU updater can no longer downgrade it
- Visual memories are actually stored in the portable build (Pillow was missing)

---

## v1.0.0 — August 2026

Bug fixes & improvements:
- **Character memory isolation**: fixed the root cause of characters' memories bleeding into the default profile — the main chat handler resolved memory once per session instead of per active character. Swept and fixed ~40 other endpoints (dream, reflect, import, delete, edit, cherish, anchor, social, lessons, reminders, visual memories, tasks, solutions) that had the same gap
- **Multi-agent chat**: fixed the default mode silently collapsing every conversation to a single agent instead of a real group conversation; name an agent to address them directly, otherwise everyone replies. Fixed a vision/mmproj cross-contamination bug when characters use different local models
- **Visual memories**: fixed images being unrecallable — the model was never given the hash it needed to show a remembered image back to you
- **Yggdrasil**: imported memories no longer sit disconnected from the graph until the next auto-consolidation cycle
- **Trigger words**: renamed the most confusable LLM tags (`cherish`→`treasure`, `deep_remember`→`recall`, `self`→`identity`) to reduce mistagging — old spellings still accepted
- **Local model backend**: added GPU/CUDA diagnostics, clear error messages when a model's architecture isn't supported by the installed llama-cpp-python build, and a guided update flow that backs up, verifies, and auto-rolls-back if a new build doesn't actually work
- **TTS**: fixed missing dependencies (edge-tts, faster-whisper) preventing voice from loading on startup
- **Context/token budget**: fixed a near-zero context headroom bug and the local GGUF worker not reloading when context length changed
- **Security**: path traversal prevention (symlink-safe), prompt injection sanitization, `tools_enabled` type validation
- **Memory**: negation-aware emotion detection, alias normalization, stats caching (60s TTL), dedup on import, batch import API
- Fixed a Gemma chat crash, server freeze during model load, silent embed failures, blank-content validation gaps, task dedup/deletion bugs, and a pre-existing `<cherish>` retroactive-tag bug (wrong keyword argument)
- 15 additional verified bugs found and fixed via a targeted audit of the proactive agent system, multi-agent chat, and models/MCP/settings

New additions:
- **Proactive agent system**: autonomous task engine, project management, tool execution with sandboxing
- **Deep Remember**: memories carry a snapshot of the full surrounding conversation, retrievable later via `<recall>`
- **Self-directed consolidation**: the model can trigger `<dream/>` and `<self_reflect/>` itself, not just on a timer
- **Self-identity memory system**: a dedicated "WHO I AM" context section, graph visualization (bounding circle + filter + stat card), separate from general/social memory
- **Time-awareness**: current date/time in context, "time since we last spoke," per-memory relative ages
- **Per-agent Visualize Memories**: every visualization now follows whichever character is active, with a dropdown to browse others
- **Multi-chat image input**: attach an image in a group conversation — routed to whichever agents' backends actually support vision, with a BLIP-caption fallback for the rest
- **Multi-chat memory parity**: agents now get the same rich context and full tag vocabulary (social impressions, treasure, recall, dream, self-reflect, reminders) as single-chat, plus proper collapsible reasoning-block rendering instead of raw `<think>` tags
- **App-wide contextual help**: hover tooltips explaining stats, navigation, visualizations, and memory actions in plain English
- Contact Dev and Report Bug links, always visible under the logo

Known issues:
- Anthropic and Google backends don't support image input yet (their `generate()` calls don't accept an `images` parameter) — affects both single-chat and multi-chat; Ollama, OpenAI, Local GGUF, and Transformers backends are unaffected
- Very new or uncommon GGUF architectures (e.g. Qwen3.5) may fail to load if the installed llama-cpp-python build predates support for them — the app now surfaces this clearly and offers a guided backend-update check, but a compatible prebuilt wheel isn't guaranteed to exist yet for every GPU generation
- Alternating between two different local (GGUF/Transformers) models across characters in multi-chat requires a full model reload each turn — inherent to running one model at a time on consumer hardware, not a bug
- The backend-update compatibility list is community-maintained and best-effort, not guaranteed current for every GPU

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
