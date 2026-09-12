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
2. Reserve one of four procedurally generated, distinct class archetypes. Every table gets a stable random draw of class names, descriptions, resource spreads, and gear variants; other players cannot reserve the same class.
3. Pick a starter weapon, prepare exactly two spells from the selected class spellbook, allocate 8 attribute points and 4 skill points, then mark ready.
4. The host starts once all joined players are ready. One player can start alone. Configured AI providers generate and validate Chapter 1 of a new original five-chapter scenario at this point; template mode uses the built-in opening chapter.
5. Explore each generated region and dungeon, investigate clues and traps, complete optional NPC side quests, and overcome an enemy before confronting the chapter boss. Three clues unlock a peaceful resolution; combat remains another path. Completing a chapter records its outcome and creates the next chapter from those consequences. Chapters 2–5 do not exist before the preceding chapter is complete.
6. Earn generated quest and encounter rewards, then use or equip applicable items in your inventory. Equipped weapons add their listed damage and maximum-resource bonuses; only one weapon can be equipped at a time. Resting and searching advance the threat clock; eight advances cause failure. State is persisted after each successful command.

Combat uses a small initiative rotation and immediate enemy retaliation. Every class has four themed spells and two preparation slots. Damage and debuff spells target the active enemy; healing, wards, and damage buffs explicitly target the caster or a party member. Movement grids, reactions, death saves, and tactical monster AI are not implemented. Template mode recognizes simple phrases; a configured model can interpret broader wording within the supported action vocabulary.

## AI and browser speech

The default template DM makes the game usable without API credentials. Administrator settings support a local llama.cpp-compatible server at `http://127.0.0.1:8080/v1` or OpenRouter's hosted chat-completions API. Enter the provider's model ID and test the connection. Hosted keys are encrypted with Fernet at rest and never returned by settings reads. A configuration version is selected when a session starts; settings changes apply to subsequently started sessions.

At session start, a configured model proposes Chapter 1 of an original five-chapter scenario containing validated locations, an objective, a guide, clues, a dungeon trap, an enemy, a boss, optional NPC side quests, rewards, and multiple endings. When the party completes a chapter, the server records its resolution, side-quest results, pressure, party health, and rewards; only then does it request the next chapter with that history as authoritative context. Later chapters must preserve prior outcomes and turn at least one consequence into new content. Generated titles are checked for reuse and every chapter is schema-validated. If generation fails, a deterministic chapter keeps the session playable and the game labels it as a fallback. The host can choose the built-in chapter while waiting; abandoned generation requests recover automatically after seven minutes.

During play, the model rewrites confirmed outcome text; the server alone resolves mechanics. When AI narration is enabled, the internal confirmed-outcome text is not displayed as a second entry. The graph provides scoped visible context. Provider failure after a committed action falls back to the confirmed text without rerolling or undoing the action. Generated prose is untrusted and never directly changes mechanics, inventory, or quest state.

Optional narration uses the browser Web Speech API (`window.speechSynthesis`). No voice model, runtime, speech assets, or TTS service is bundled or downloaded. Playback is local to each player’s device, and gameplay continues with text if browser speech is unavailable or fails.

## Persistence and correctness

PostgreSQL `sessions` stores authoritative JSON state; `events` records commands and full post-command snapshots for this small prototype. `entities` and `relationships` are a relational property graph materialized transactionally with game changes. Apache AGE is not installed in this first build; Cypher traversal can be added without introducing another database. The graph is not a second independent mechanical authority.

Session row locks serialize mutations. Expected versions reject stale commands, and unique command IDs make retries idempotent. The API filters other players' drafts/inventories out of views. Clients currently refresh shared state every 2.5 seconds; WebSocket delivery is planned. Cookie identities survive reconnects on the same browser. Account-based recovery across devices, late joining, and private scenes are not yet implemented.

## Validation

```powershell
docker compose -f compose.test.yaml up -d --wait
./.venv/Scripts/python.exe -m pytest -q
cd web
node node_modules/typescript/bin/tsc --noEmit
node node_modules/vinext/dist/cli.js build
```

Integration tests use the disposable PostgreSQL 17 service in `compose.test.yaml`, bound only to `127.0.0.1:55433`. The test harness never reads `DATABASE_URL` from `.env` and rejects non-local `TEST_DATABASE_URL` values, preventing accidental access to Neon or another remote database. Set `TEST_DATABASE_URL` only when intentionally using a different local PostgreSQL test instance. The suite covers capacity, class races, build validation, item idempotency, encrypted secrets, generated-scenario validation, playtest-content rejection, side-quest rewards, encounter progression, privacy, graph updates, and scenario endings. Browser interaction and audio quality testing are separate from these checks.

Stop and discard the test database when finished:

```powershell
docker compose -f compose.test.yaml down
```

## Next implementation milestones

- Broader free-text action support, richer multi-encounter procedural worlds, per-NPC memory, and tested model capability profiles.
- WebSocket updates, explicit reaction windows, private player scenes, inventory transfers, and campaign management.
- Class ability composition and balance beyond the four starter archetypes; full selected ruleset support.
- Admin provider management, endpoint policies, task-specific models, budgets, key revocation, configuration rollback, and production authentication.
- Expanded browser narration controls and tested browser compatibility.

The local HTTP cookie setup is for development. Public hosting requires HTTPS/secure cookies, deployment-managed secrets, persistent account authentication, and operational limits. Nothing has been published externally.

## Deploy the Docker image with Neon

The production image contains both the statically exported web app and the FastAPI server, and exposes one HTTP port. PostgreSQL is not included in the image. On startup, the API safely creates the required tables in Neon; concurrent replicas serialize this setup with a PostgreSQL advisory lock.

1. In Neon, copy the **pooled** connection string. Keep `sslmode=require&channel_binding=require` in the URL.
2. Copy `.env.production.example` to `.env.production`, replace every placeholder, and set `APP_ORIGIN` to the public HTTPS origin without a trailing slash. Never commit this file.
3. Generate `SECRET_KEY` with the command shown in the example file. Preserve this key across deployments and alongside database backups, because it encrypts stored AI provider credentials.
4. Build and start the service:

```powershell
docker compose --env-file .env.production -f compose.production.yaml up -d --build
docker compose --env-file .env.production -f compose.production.yaml ps
```

The default host port is `8000`; set `APP_PORT` in `.env.production` to change it. Check readiness at `/api/health`. Put the service behind an HTTPS reverse proxy or a container platform that terminates TLS. The deployment manifest enables secure cookies, so browser sessions intentionally require HTTPS.

For a platform that accepts a Dockerfile directly, build from the repository root and configure `DATABASE_URL`, `ADMIN_PASSWORD`, `SECRET_KEY`, `APP_ORIGIN`, and `COOKIE_SECURE=true` as runtime secrets or environment variables. The image honors the platform-provided `PORT` value and runs as an unprivileged user. Do not pass build-time secrets or bake an environment file into the image.

### Neon project policy

The repository includes `neon.ts`, a bare Postgres-only policy for Neon project `noisy-cloud-08360518`. The local `.neon` link context and the database URLs pulled into `.env` are intentionally ignored by Git and Docker.

To link a fresh checkout and apply the policy:

```powershell
npm install --global neon@latest
neon auth
neon link --project-id noisy-******-******** --branch production -y
neon config plan
neon deploy
```

Neon Skills and MCP installation are optional development tooling; they are not required to build or run the application. The FastAPI startup process creates the application schema transactionally on the linked database.
