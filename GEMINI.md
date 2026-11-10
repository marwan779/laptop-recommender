# Git Rules and Workflow Guidelines

## General Workflow Rules

* **Do not commit or push any changes unless explicitly instructed by the user.** Never run `git commit`, `git push`, or create commits proactively without explicit user confirmation.

## Git Commit Message Rules

Always follow these rules when creating, suggesting, or reviewing Git commit messages.

## Format

Use Conventional Commits:

`<type>(<scope>): <description>`

The scope is optional. Use it when it provides useful context.

## Types

* `feat` — new functionality or a backward-compatible feature
* `fix` — bug fix or correction of incorrect behavior
* `perf` — performance improvement
* `refactor` — code restructuring without changing behavior
* `test` — adding or modifying tests
* `docs` — documentation-only changes
* `build` — build system or dependency changes
* `ci` — CI/CD changes
* `chore` — general maintenance
* `style` — formatting-only changes with no logic changes
* `revert` — revert a previous commit

## Scope

Use a scope when the affected area is clear.

Examples:

`feat(api): add health check endpoint`

`fix(auth): handle expired refresh tokens`

`test(order): add order validation tests`

`ci(github-actions): add mutation testing workflow`

If no meaningful scope exists, omit it:

`fix: handle null response`

## Description

* Keep it concise and specific.
* Describe what changed, not how every implementation detail was handled.
* Use lowercase.
* Do not end the description with a period.
* Avoid vague descriptions such as `update`, `changes`, `fix stuff`, or `improvements`.
* Do not invent changes that are not present in the actual diff.

## Breaking Changes

If the change breaks existing behavior, an existing API, contract, or compatibility, mark it explicitly with `!`.

Example:

`feat(api)!: change authentication response format`

A `BREAKING CHANGE` footer may also be used when additional explanation is necessary.

## Semantic Versioning

When Conventional Commits are used with semantic-release:

* `fix` → PATCH
* `perf` → PATCH
* `feat` → MINOR
* `feat!` → MAJOR
* `fix!` → MAJOR
* `BREAKING CHANGE` → MAJOR

Normally these do not trigger a release:

* `docs`
* `test`
* `refactor`
* `build`
* `ci`
* `chore`
* `style`

Never put `major`, `minor`, or `patch` in the commit message.

Incorrect:

`minor: add health check endpoint`

Correct:

`feat(api): add health check endpoint`

## Choosing the Type

Determine the primary purpose of the actual changes before writing the commit message.

* Added new functionality → `feat`
* Fixed existing incorrect behavior → `fix`
* Improved performance → `perf`
* Restructured code without changing behavior → `refactor`
* Changed tests → `test`
* Changed documentation → `docs`
* Changed CI/CD → `ci`
* Changed build/dependencies → `build`
* General maintenance → `chore`
* Formatting only → `style`
* Breaking existing behavior/API → add `!`

Do not use `feat` merely because code was added.

Do not use `fix` unless existing incorrect behavior was actually corrected.

## When Generating a Commit Message

When asked to create a commit message:

1. Inspect the Git diff and relevant changes when available.
2. Determine the primary purpose of the change.
3. Select the correct type.
4. Select an appropriate scope when useful.
5. Determine whether the change is breaking.
6. Generate a concise Conventional Commit message.
7. Ensure the message accurately represents the actual changes.

If the changes contain unrelated modifications, prefer separate commit messages rather than one vague message.

## Final Validation

Before returning a commit message, verify:

* Correct type
* Useful and accurate scope
* Clear description
* Concise wording
* Lowercase description
* No unnecessary punctuation
* Breaking changes are explicitly marked
* No `major`, `minor`, or `patch` labels
* Message accurately reflects the actual diff

---

# Audit & Verification Rules

## Mandatory Live Full-Catalog Full-Spec Audit Protocol

* **Live Network Requirement**: Never run an audit against cached JSON files, local dictionary dumps, or pre-scraped files. An audit MUST fetch the raw live PDP HTML directly over the network from the actual store URLs.
* **Full Catalog Scope**: Never limit an audit to a subset, sample, or partial batch of laptops unless explicitly instructed by the user. Every audit MUST evaluate 100% of the laptops in the catalog.
* **All Specifications Scope**: Never restrict an audit to only "core" specifications (e.g., just CPU, RAM, GPU, Storage). The audit MUST verify every specification dimension across all 35+ fields:
  1. **Identity**: `brand`, `laptop_family`, `laptop_model`, `manufacturer_part_number`
  2. **CPU**: `manufacturer`, `line`, `model`, `cores`, `threads`, `clock_speed`
  3. **GPU**: `manufacturer`, `model`, `vram_gb`, `tdp_w`, `integrated`
  4. **Memory**: `capacity_gb`, `memory_type`, `speed`, `slot_count`, `max_supported_gb`
  5. **Storage**: `capacity_gb`, `storage_type`, `interface`, `form_factor`, `slot_count`
  6. **Display**: `size_inches`, `resolution`, `refresh_rate_hz`, `panel_type`, `aspect_ratio`, `touchscreen`
  7. **Power & Battery**: `battery_capacity_wh`, `power_adapter_w`, `battery_cells`
  8. **Physical**: `weight_kg`, `color`, `width_mm`, `depth_mm`, `height_mm`
  9. **Build & Security**: `has_backlit_keyboard`, `has_fingerprint`, `pointing_device`, `security_features`
  10. **Audio & Webcam**: `speaker_count`, `microphone`, `webcam.resolution`
  11. **Connectivity**: `wifi`, `bluetooth`, `ethernet`, `ports`
* **Raw Live DOM Ground Truth**: Compare extracted structured data directly against the raw un-sanitized HTML/DOM content of the live page (including raw attributes like `data-raw-spec`, dynamic scripts, and collapsible tab disclosures) to guarantee zero undetected misses or hallucinations.
---

# Clean Architecture & SOLID Principles Enforcement Rules

## Mandatory 3-Tier Layering Separation

Every feature, service, or refactoring added to the codebase MUST strictly adhere to Clean Architecture:

1. **Domain Layer (`app/domain/`) — Pure Business Logic & Math**:
   - **Zero External Dependencies**: Absolutely NO database imports (no SQLAlchemy, asyncpg, psycopg), NO web framework imports (no FastAPI, Starlette), NO network client imports (no httpx, requests).
   - **Pure Logic**: Contains pure Python dataclasses, domain entities, business policies, and mathematical algorithms (e.g., pricing evaluation, score calculations, hardware tiering).
   - **Instant Testability**: Must be 100% unit-testable in isolation in milliseconds without spinning up PostgreSQL, test containers, or mocking database sessions.

2. **Repository / Infrastructure Layer (`app/repositories/`, `app/common/storage/`) — Data Access**:
   - Encapsulates all SQL execution, SQLAlchemy queries, ORM sessions, and external object storage (S3).
   - All database access MUST go through dedicated repositories (e.g., `LaptopRepository`, `OfferRepository`, `BatchLogRepository`).
   - Services and controllers are strictly forbidden from writing inline SQL statements (`select()`, `session.get()`, `update()`) or managing session transactions directly.

3. **Application / Use Case Layer (`app/services/`, `app/jobs/`) — Orchestration**:
   - Coordinates domain services and repositories to fulfill specific application workflows.
   - Injects domain policies into repository results.
   - Contains NO raw SQL queries and NO embedded mathematical formulas.

## SOLID Principles Compliance Checklist

Before finalizing any implementation, verify:
* **Single Responsibility (SRP)**: Each class/module has exactly one reason to change. Data access, domain math, and API serialization are never mixed in the same file.
* **Open/Closed (OCP)**: Code is open for extension (e.g., new store scrapers, new scoring dimensions) via interfaces and polymorphism, but closed for modification.
* **Liskov Substitution (LSP)**: Subclasses or interface implementations honor the base contract without unexpected side effects.
* **Interface Segregation (ISP)**: Clients depend only on the methods they use. Repositories expose focused, granular operations.
* **Dependency Inversion (DIP)**: High-level business logic never depends on low-level database details. High-level policies depend on abstractions, and dependencies are injected.


---

# Frontend UI Design System ("The Verified Instrument")

All frontend UI work in `frontend/` MUST strictly follow the full specification in `.agent/rules/design-system.md`:

* **Surface & Border Tokens**: Dark-first hardware workbench hierarchy (`--bg-app: #0A0E13`, `--bg-surface: #10161D`, `--bg-raised: #151D27`, `--bg-overlay: #1A2431`, `--bg-input: #0D131A`) with `1px solid` structural hairlines (`--border-subtle: #1E2836`, `--border-strong: #2B394C`).
* **Studio Lightbox Well (`--studio-well: #EDEBE6`)**: The only light surface in the app—a `4:3` rounded (`8px`) padded container (`object-fit: contain`) that grounds white-background store product photos cleanly inside dark cards.
* **Strict 4-Rule Color Discipline (1 Job Per Color)**:
  1. **Cairo Gold (`#E9B949` / `#F5C95C`)**: Money & decisions ONLY (Primary CTA buttons, EGP prices, TOPSIS Match `%`, Rank `#1`, active persona border, active view segment, budget slider). Maximum one solid gold focal element per card.
  2. **Telemetry Cyan (`#22D3EE`)**: Hardware benchmarks & data ONLY (`1–100` score bar fills with `50%`/`80%` ticks, metric sliders, spec bullet dots, persona icon wells). Never use on buttons or prices.
  3. **Signal Indigo (`#818CF8`)**: Machine intelligence provenance tags ONLY (`TOPSIS`, `AI Review Synthesis`, `NLP` badges).
  4. **Emerald (`#34D399`) & Rose (`#F87171`)**: Verification & judgement ONLY (Live dot, `BEST PRICE` outline chip, Pros `+` vs. Cons `-`, score numerals `< 50`).
* **Typography & Tabular Numerals**: `Space Grotesk` (`--font-display`) for headings, prices, and scores; `Inter` (`--font-ui`) for UI/specs; `IBM Plex Mono` (`--font-mono`) for MPNs, `#rank`, and timestamps; `IBM Plex Sans Arabic` (`--font-arabic`) for Arabic text (`dir="auto"`, Western digits `0–9`). Always enforce `font-variant-numeric: tabular-nums` on prices, scores, and counters.
* **UI-Only Boundary**: Never alter UX flows, component props, state hooks, or API contracts during visual styling updates unless explicitly requested.
