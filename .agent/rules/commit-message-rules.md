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
