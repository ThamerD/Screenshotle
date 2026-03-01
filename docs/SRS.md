# Screenshotle – Software Requirements Specification

## 1. Overview

**Screenshotle** is a browser-based guessing game: the player sees one screenshot from a video game, guesses the title, and gets hints (Generation and Genre) when wrong. No sign-up or login.

- **Stack:** Python, FastAPI, Jinja2, vanilla JS. Data from IGDB API; hints via OpenAI API. Deploy on Render (or self-host).
- **Audience:** This document is for developers implementing and maintaining the project.

---

## 2. Requirements

### What the app does

1. **New game** – Pick a random game from a pool of popular games (IGDB). Show one screenshot and ask for the game name.
2. **Guess** – User submits a guess. If it matches the correct game (fuzzy match allowed), show “You win” and offer “Play again”. If not, show hints then the next screenshot for the same game; repeat until correct or max attempts.
3. **Hints** – Only two types:
   - **Generation** – Console era from release date (e.g. “Eighth generation (2012–present)”); may mention primary consoles (e.g. “Think PlayStation 4, Xbox One, Nintendo Switch”).
   - **Genre** – High-level genre from IGDB (e.g. Action, RPG).
4. **Session** – Current game, screenshot index, and attempt count live in server-side session. No user accounts.

### What the app needs

- **IGDB API** (Twitch client id/secret) for games, screenshots, genres, and release dates. Optionally cache the popular-games list.
- **OpenAI API** (key) to compare guess to correct name and to generate hint text.
- **Env vars** for secrets (no secrets in repo).

---

## 3. Modules

The codebase is split into **modules** so each can be developed and tested on its own. Dependencies flow one way where possible: routes → services → clients.

| Module | Purpose | Depends on |
|--------|---------|------------|
| **`app`** | Entry point (`main.py`), app creation, config (env). | — |
| **`app.models`** | Data shapes only: e.g. Game, Session, HintRequest. No DB, no API calls. | — |
| **`app.clients`** | Talk to external APIs. `igdb_client`: Twitch auth, fetch games/screenshots/genres. `openai_client`: compare guess, generate hint text. | `app.models` (for request/response shapes) |
| **`app.services`** | Gameplay logic: pick random game, resolve generation from release date, build session state, call clients for hints. | `app.models`, `app.clients` |
| **`app.routes`** | HTTP endpoints: new game, submit guess, play again. Render Jinja2 templates; read/write session. | `app.models`, `app.services` |

Templates and static files live at project root: `templates/`, `static/`.

Each module should have a **single, clear responsibility**. New behaviour goes in the module that owns that responsibility.

---

## 4. Development Instructions

### 4.1 Implement and test by module

- Develop **one module at a time** and add **unit tests** for that module before moving on.
- Unit tests must **mock** dependencies (e.g. mock `app.clients` when testing `app.services`). Keep tests fast and isolated.
- Add **integration tests** that wire real modules together (e.g. route → service → client with mocks for IGDB/OpenAI). Cover at least one full flow (e.g. start game → get screenshot → submit wrong guess → get hints).
- Use a single command to run all tests (e.g. `pytest`).

### 4.2 Comments

- Add **comments** where they help readability: module/class purpose, non-obvious logic, and important invariants. Keep comments in sync with the code.

### 4.3 Git

- Use **meaningful commit messages** and **short, focused commits**.
- Work on **branches** for features/fixes; keep the default branch deployable.
- **Do not commit** secrets or `.env`; list ignored paths in `.gitignore`.

---

## 5. References

- [Wikipedia: History of video game consoles – Console generations](https://en.wikipedia.org/wiki/History_of_video_game_consoles#Console_generations) (for Generation buckets and primary consoles).
- [IGDB API](https://api-docs.igdb.com/) (Twitch OAuth2; games, screenshots, genres, release dates).
