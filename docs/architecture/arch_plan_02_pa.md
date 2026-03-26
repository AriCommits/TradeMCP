# Architecture Plan 02A: Pathing, Typing Gates, Metadata, and Markdown Reporting

Date: 2026-03-26

## Scope

This plan focuses on operational hardening and maintainability upgrades on top of Plan 01 work:

- finish migration to repo-relative paths with `pathlib`
- centralize directory/config path resolution in one Python module
- add adapter `Protocol` contracts and enforce router typing
- add staged CI typing gates (`mypy` + `pyright`)
- persist deterministic run metadata in every artifact bundle
- add lightweight markdown-first backtest reporting with optional HTML summary tables

Backtest suite taxonomy and phased feature expansion are detailed in:

- `docs/architecture/arch_plan_02_pb.md`

## Prioritized Build Plan

1. Add centralized path module (`pathlib`-first)
- Create a typed path resolver module that defines directory names as relative paths from repo root.
- Expose a canonical resolver used by scripts and core modules.
- Remove repeated script bootstrap path logic where possible.

2. Finish absolute-path migration
- Replace remaining hardcoded absolute paths with repo-relative defaults.
- Normalize all path inputs at boundaries to `Path` objects.
- Keep CLI override support for custom paths.

3. Add adapter protocol contracts + router typing
- Introduce typed adapter protocols for read and execution capabilities.
- Use these protocols in router internals to tighten static type safety.
- Keep runtime behavior backwards-compatible while improving contract clarity.

4. Add staged typing CI gates
- Add GitHub Actions checks for `ruff`, `mypy`, `pyright`, `pytest`.
- Stage strictness to fail on changed files first.
- Run full-repo typing checks in informational mode until debt is reduced.

5. Add deterministic run metadata to artifacts
- Persist `run_metadata.json` in every artifact bundle.
- Required fields:
- `run_id`
- `timestamp_utc`
- `seed`
- `config_path`
- `config_hash`
- `git_commit`
- `python_version`
- `command`
- `user_meta` (user-supplied dictionary)

6. Add markdown-first report generator
- Default report format is markdown for narrative and key sections.
- Use HTML tables only for compact top-N summary ranking sections.
- Keep image outputs as PNGs and reference them from markdown.

## Interface Additions

- Path module:
- `DirectoryLayout` (relative names only)
- `ProjectPaths` (resolved absolute paths)
- `resolve_paths()`

- Metadata model:
- `RunMetadata` with extensible `user_meta: dict[str, Any]`

- Adapter contracts:
- `AdapterReadProtocol`
- `AdapterExecutionProtocol`

## Defaults Chosen

- Path management is `pathlib`-first.
- Directory structure is represented in Python as relative path names.
- CI platform is GitHub Actions.
- Typing rollout is staged: blocking for changed files first.
- Report format is markdown-first with selective HTML tables.

## Validation

1. Pathing checks
- No runtime defaults depend on machine-specific absolute paths.
- Scripts and modules resolve directories via centralized path module.

2. Typing checks
- `mypy` and `pyright` jobs run in CI.
- changed-file lane fails on new typing regressions.

3. Metadata checks
- artifact-producing commands always write `run_metadata.json`.
- `user_meta` payload is preserved verbatim when provided.

4. Reporting checks
- markdown reports render with linked/embedded PNG outputs.
- top-N ranking table uses HTML when enabled.
