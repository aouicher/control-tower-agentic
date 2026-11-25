#!/usr/bin/env python3
"""Render a template tree into a destination, replacing {{ct.*}} tokens.

Standard library only (Python 3.8+). Idempotent and safe by default:
  * existing destination files are never overwritten unless --force is given;
    with --force the old file is first copied to <dst>/.control-tower-backup/<timestamp>/
  * Obsidian placeholders such as {{title}} and {{date:YYYY-MM-DD}} are left untouched
  * an unknown {{ct.xxx}} token is an error (nothing is written)
  * files ending in .tmpl lose that suffix (CLAUDE.md.tmpl -> CLAUDE.md)

Tokens:
  {{ct.team}} {{ct.teams}} {{ct.Team}} {{ct.Teams}}      (same for workstream, risk, person/people)
  {{ct.owner_name}} {{ct.owner_handle}} {{ct.timezone}} {{ct.vault_path}}   (from the answers file)

Usage:
  python3 installer/render.py --src core/vault --dst ~/my-vault \
      --vocab core/vocabulary.json [--vocab packs/engineering/vocabulary.json] \
      --answers answers.json [--dry-run] [--force]
"""
import argparse
import datetime
import json
import os
import re
import shutil
import sys

TOKEN = re.compile(r'\{\{ct\.([A-Za-z_]+)\}\}')
SCALARS = ('owner_name', 'owner_handle', 'timezone', 'vault_path')
TEXT_EXT = {'.md', '.base', '.json', '.yml', '.yaml', '.txt', '.tmpl', '.sh', '.py', '.plist', '.canvas', ''}


def build_table(vocab_files, answers):
    vocab = {}
    for path in vocab_files:
        data = json.load(open(path, encoding='utf-8'))
        for key, val in data.items():
            if key.startswith('_'):
                continue
            vocab[key] = {**vocab.get(key, {}), **val}
    table = {}
    for key, forms in vocab.items():
        for form in ('singular', 'plural'):
            if form not in forms:
                raise SystemExit(f'vocabulary entry "{key}" has no "{form}" form')
        for name, word in ((key, forms['singular']), ({'person': 'people'}.get(key, key + 's'), forms['plural'])):
            table[name] = word
            table[name[0].upper() + name[1:]] = word[0].upper() + word[1:]
    for key in SCALARS:
        if key in answers:
            table[key] = str(answers[key])
    return table


def render_text(text, table, rel, errors):
    def sub(match):
        name = match.group(1)
        if name not in table:
            errors.append(f'{rel}: unknown token {{{{ct.{name}}}}}')
            return match.group(0)
        return table[name]
    return TOKEN.sub(sub, text)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--src', required=True)
    ap.add_argument('--dst', required=True)
    ap.add_argument('--vocab', action='append', required=True)
    ap.add_argument('--answers', default=None)
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--force', action='store_true')
    args = ap.parse_args()

    answers = json.load(open(args.answers, encoding='utf-8')) if args.answers else {}
    answers.setdefault('vault_path', os.path.abspath(os.path.expanduser(args.dst)))
    table = build_table(args.vocab, answers)
    src = os.path.abspath(args.src)
    dst = os.path.abspath(os.path.expanduser(args.dst))
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')

    plan, errors = [], []
    for root, _, files in os.walk(src):
        for name in sorted(files):
            s = os.path.join(root, name)
            rel = os.path.relpath(s, src)
            out_rel = rel[:-5] if rel.endswith('.tmpl') else rel
            target = os.path.join(dst, out_rel)
            if os.path.splitext(name)[1].lower() in TEXT_EXT:
                try:
                    content = render_text(open(s, encoding='utf-8').read(), table, rel, errors)
                except UnicodeDecodeError:
                    content = None
            else:
                content = None
            plan.append((s, target, out_rel, content))
    if errors:
        print('\n'.join(errors), file=sys.stderr)
        sys.exit(2)

    created = skipped = replaced = 0
    for s, target, out_rel, content in plan:
        exists = os.path.exists(target)
        if exists and not args.force:
            skipped += 1
            continue
        if args.dry_run:
            print(('replace ' if exists else 'create  ') + out_rel)
            created += not exists
            replaced += exists
            continue
        os.makedirs(os.path.dirname(target), exist_ok=True)
        if exists:
            backup = os.path.join(dst, '.control-tower-backup', stamp, out_rel)
            os.makedirs(os.path.dirname(backup), exist_ok=True)
            shutil.copy2(target, backup)
            replaced += 1
        else:
            created += 1
        if content is None:
            shutil.copy2(s, target)
        else:
            open(target, 'w', encoding='utf-8').write(content)
    mode = 'dry run: ' if args.dry_run else ''
    print(f'{mode}{created} created, {replaced} replaced, {skipped} kept (already existed)')


if __name__ == '__main__':
    main()
