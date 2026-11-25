# Examples

Everything here is fictional: **Acme**, a made-up company, and **Sam Rivera**, a made-up user.

## Answers files

`examples/answers/<pack>.json` install one pack with its first listed tool per capability. `minimal-no-tools.json` installs the product pack with no tools and no schedule: the safest first try.

```bash
python3 installer/install.py --answers examples/answers/minimal-no-tools.json --dry-run
```

Edit `vault_path` first if you do not want the vault in your home folder.

## Sample notes

Everything below is fictional (Acme, Sam Rivera, Casey Doe). Replace `<your vault>` with your vault folder, for example the `vault_path` of your answers file.

`examples/acme-notes/` holds three finished notes (a project, a team, a decision) showing the core property conventions. After installing, copy them into your vault to see the cockpit and dashboards populated:

```bash
cp -R examples/acme-notes/. "<your vault>"/
```

`examples/pack-notes/<pack>/` holds sample notes for a profile, in the same folders as in the vault:

| Pack | Notes |
|---|---|
| `marketing` | two campaigns (one active, one draft) in `work/workstreams/growth/`, three content pieces in `work/content/` |
| `product` | one opportunity in `work/opportunities/`, one anonymised interview in `library/interviews/` |

```bash
cp -R examples/pack-notes/marketing/. "<your vault>"/
cp -R examples/pack-notes/product/. "<your vault>"/
```

Copy only the packs you installed. `cp -R` overwrites files with the same name: check before copying into a vault you already use.

## Demo vault

`build_demo_vault.py` runs the real installer into a new folder, then adds about 50 fictional Acme notes dated relative to today, so every cockpit page and dashboard has content (used for the README screenshots): `python3 examples/build_demo_vault.py --out ~/control-tower-demo`.
Options: `--packs engineering,product`, `--date YYYY-MM-DD`, `--force` (rebuild a previous demo), `--tasks-plugin-dir <installed obsidian-tasks-plugin folder>` (copies a local Tasks plugin; nothing is downloaded). Nothing is scheduled.
