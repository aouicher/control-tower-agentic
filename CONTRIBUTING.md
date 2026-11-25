# Contributing

## Ground rules

- Everything in this repository is in English.
- No private names, company specifics, secrets or real customer data. Run `python3 tools/scan-leaks.py` before every commit; add private terms to your local, git-ignored `.denylist.local`.
- Standard library only for installer and scheduler code (Python 3.9+, for `zoneinfo`).
- Jobs and adapters stay read-only on external systems.

## Tests

```bash
python3 -W ignore -m unittest discover -s tests -p "test_*.py"
```

Tests run in temporary directories: they never touch your real vault, `~/.claude`, launchd or crontab. Before a pull request also run `python3 tests/e2e/run_e2e.py`; see [docs/testing.md](docs/testing.md) for the container test.

## Adding a pack

Follow [docs/design/pack-spec.md](docs/design/pack-spec.md): `pack.json`, `vocabulary.json`, `vault/`, `jobs/<id>/{job.json,prompt.md}`, `routines/`, a README. Packs may add folders and types but never edit `CLAUDE.md`. The suite checks collisions, tokens and permissions.

## Adding an adapter

Add `adapters/<capability>/<tool>.md` and `.json` following the capability `contract.md`. Permissions must be exact: no MCP wildcard, Bash rules as `Bash(cmd sub:*)`. If the tool cannot be read-only, write a `read_only_mitigation`. Mark `status: documented` until verified on a live account.

## Commits

English Conventional Commits: `type(scope): subject`.
