# Examples

Everything here is fictional: **Acme**, a made-up company, and **Sam Rivera**, a made-up user.

## Answers files

`examples/answers/<pack>.json` install one pack with its first listed tool per capability. `minimal-no-tools.json` installs the product pack with no tools and no schedule: the safest first try.

```bash
python3 installer/install.py --answers examples/answers/minimal-no-tools.json --dry-run
```

Edit `vault_path` first if you do not want the vault in your home folder.

## Sample notes

`examples/acme-notes/` holds three finished notes (a project, a team, a decision) showing the property conventions. After installing, copy them into your vault to see the cockpit and dashboards populated:

```bash
cp -R examples/acme-notes/. ~/control-tower-minimal/
```
