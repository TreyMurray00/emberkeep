# Emberkeep

A local, D&D-inspired cooperative RPG prototype for one to four players. This is an executable first slice of the architecture, using original homebrew mechanics rather than full D&D/SRD coverage.

## Run locally on Windows

Prerequisites: Docker Desktop (Linux containers), Python 3.12+, Node.js 22.13+, and pnpm 9.11.0. The dependency lockfiles are committed for repeatable installation.

```powershell
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.lock.txt
./.venv/Scripts/python.exe server/setup_local.py
cd web
pnpm install --frozen-lockfile
cd ..
./scripts/Start-Local.ps1
```

The setup script creates unique local credentials in `.env` without overwriting existing ones. The database is PostgreSQL 17 in Docker, bound only to `127.0.0.1:55432`, with a persistent named volume. The app initializes its schema on API startup. No cloud database is involved.

Open http://127.0.0.1:5173/ for the game and http://127.0.0.1:5173/admin/ai for settings. Read `ADMIN_PASSWORD` in `.env` to sign in as administrator. Do not commit or share that file. The admin key-encryption secret is also there; keep it with database backups.

For foreground development, run these in separate terminals from the repository root:

```powershell
docker compose up -d --wait
./.venv/Scripts/python.exe -m uvicorn server.app:app --host 127.0.0.1 --port 8000 --reload
```

```powershell
cd web
node node_modules/vinext/dist/cli.js dev
```

The UI proxies `/api` to FastAPI. All services are local-only by default. Use separate browser profiles for independent players; ordinary tabs share a character cookie. Share the ten-character table code to join the same lobby. This setup does not expose the app to other computers yet.

## Play the first adventure

1. Create a table and name your character, or enter an existing invitation code.
2. Reserve one of four randomly named, distinct class archetypes. Other players cannot reserve the same class.
3. Pick a starter weapon, allocate 8 attribute points and 4 skill points, then mark ready.
4. The host starts once all joined players are ready. One player can start alone. Configured AI providers generate and validate Chapter 1 of a new original five-chapter scenario at this point; template mode uses the built-in opening chapter.
5. Explore each generated region and dungeon, investigate clues and traps, complete optional NPC side quests, and overcome an enemy before confronting the chapter boss. Three clues unlock a peaceful resolution; combat remains another path. Completing a chapter records its outcome and creates the next chapter from those consequences. Chapters 2–5 do not exist before the preceding chapter is complete.
6. Earn generated quest and encounter rewards, then use or equip applicable items in your inventory. Resting and searching advance the threat clock; eight advances cause failure. State is persisted after each successful command.

Combat currently uses a small initiative rotation and immediate guardian retaliation. Movement grids, reactions, full spell lists, death saves, and tactical monster AI are not implemented. Buttons and the text-action box both resolve to the same six supported action types. Template mode recognizes simple phrases; a configured model can interpret broader wording within that action vocabulary.

## AI and browser speech

The default template DM makes the game usable without API credentials. Administrator settings support a local llama.cpp-compatible server at `http://127.0.0.1:8080/v1` or OpenRouter's hosted chat-completions API. Enter the provider's model ID and test the connection. Hosted keys are encrypted with Fernet at rest and never returned by settings reads. A configuration version is selected when a session starts; settings changes apply to subsequently started sessions.

At session start, a configured model proposes Chapter 1 of an original five-chapter scenario containing validated locations, an objective, a guide, clues, a dungeon trap, an enemy, a boss, optional NPC side quests, rewards, and multiple endings. When the party completes a chapter, the server records its resolution, side-quest results, pressure, party health, and rewards; only then does it request the next chapter with that history as authoritative context. Later chapters must preserve prior outcomes and turn at least one consequence into new content. Generated titles are checked for reuse and every chapter is schema-validated. If later generation fails, a consequence-aware deterministic chapter keeps the session playable.

During play, the model rewrites confirmed outcome text; the server alone resolves mechanics. When AI narration is enabled, the internal confirmed-outcome text is not displayed as a second entry. The graph provides scoped visible context. Provider failure after a committed action falls back to the confirmed text without rerolling or undoing the action. Generated prose is untrusted and never directly changes mechanics, inventory, or quest state.

Kokoro.js runs q8/WASM inference in a browser Web Worker. Enable voice to download the model/runtime/voice files and read narration locally. The initial download can be substantial; device memory and CPU affect speed. Player text is not sent to a TTS server. The prototype obtains model assets from upstream Hugging Face/CDN sources; self-hosting and pinning those assets are still required for an offline-distribution release. Speech is optional and gameplay continues on synthesis failure. Actual audio playback must be checked on the target browsers/devices.

## Persistence and correctness

PostgreSQL `sessions` stores authoritative JSON state; `events` records commands and full post-command snapshots for this small prototype. `entities` and `relationships` are a relational property graph materialized transactionally with game changes. Apache AGE is not installed in this first build; Cypher traversal can be added without introducing another database. The graph is not a second independent mechanical authority.

Session row locks serialize mutations. Expected versions reject stale commands, and unique command IDs make retries idempotent. The API filters other players' drafts/inventories out of views. Clients currently refresh shared state every 2.5 seconds; WebSocket delivery is planned. Cookie identities survive reconnects on the same browser. Account-based recovery across devices, late joining, and private scenes are not yet implemented.

## Validation

```powershell
./.venv/Scripts/python.exe -m pytest -q
cd web
node node_modules/typescript/bin/tsc --noEmit
node node_modules/vinext/dist/cli.js build
```

Integration tests create/use a separate `emberkeep_test` database in the local container and delete the sessions/config versions they create. They do not modify the live `emberkeep` database. They cover capacity, class races, build validation, item idempotency, encrypted secrets, generated-scenario validation, playtest-content rejection, side-quest rewards, encounter progression, privacy, graph updates, and scenario endings. Browser interaction and audio quality testing are separate from these checks.

## Next implementation milestones

- Broader free-text action support, richer multi-encounter procedural worlds, per-NPC memory, and tested model capability profiles.
- WebSocket updates, explicit reaction windows, private player scenes, inventory transfers, and campaign management.
- Class ability composition and balance beyond the four starter archetypes; full selected ruleset support.
- Admin provider management, endpoint policies, task-specific models, budgets, key revocation, configuration rollback, and production authentication.
- Self-hosted pinned speech assets, optional WebGPU, NPC-specific voice playback, and tested browser compatibility.

The local HTTP cookie setup is for development. Public hosting requires HTTPS/secure cookies, deployment-managed secrets, persistent account authentication, and operational limits. Nothing has been published externally.
