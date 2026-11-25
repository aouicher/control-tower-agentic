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
  {{ct.owner_name}} {{ct.owner_handle}} {{ct.timezone}} {{ct.vault_path}}   (from the answers)

Usage:
  python3 installer/render.py --src core/vault --dst ~/my-vault \
      --vocab core/vocabulary.json [--vocab packs/engineering/vocabulary.json] \
      --answers answers.json [--dry-run] [--force] [--fail-on-collision]
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import sys

TOKEN = re.compile(r'\{\{ct\.([A-Za-z_]+)\}\}')
SCALARS = ('owner_name', 'owner_handle', 'timezone', 'vault_path')
TEXT_EXT = {'.md', '.base', '.json', '.yml', '.yaml', '.txt', '.tmpl', '.sh', '.py', '.plist', '.canvas', ''}


class RenderError(Exception):
    pass


def build_table(vocab_files, answers):
    vocab = {}
    for path in vocab_files:
        with open(path, encoding='utf-8') as fh:
            data = json.load(fh)
        for key, val in data.items():
            if key.startswith('_'):
                continue
            vocab[key] = {**vocab.get(key, {}), **val}
    table = {}
    for key, forms in vocab.items():
        for form in ('singular', 'plural'):
            if form not in forms:
                raise RenderError(f'vocabulary entry "{key}" has no "{form}" form')
        plural_name = {'person': 'people'}.get(key, key + 's')
        for name, word in ((key, forms['singular']), (plural_name, forms['plural'])):
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


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def render_tree(src, dst, table, dry_run=False, force=False, fail_on_collision=False, rename=None):
    """Render src into dst. Returns {'created': [...], 'replaced': [...], 'kept': [...]} (relative paths).

    `rename` is an optional function(relative_output_path) -> relative_output_path, used by the installer
    to place files (for example prompt.md.tmpl -> prompt.md).
    """
    src = os.path.abspath(src)
    dst = os.path.abspath(os.path.expanduser(dst))
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    plan, errors = [], []
    for root, _, files in os.walk(src):
        for name in sorted(files):
            s = os.path.join(root, name)
            rel = os.path.relpath(s, src)
            out_rel = rel[:-5] if rel.endswith('.tmpl') else rel
            if rename:
                out_rel = rename(out_rel)
            content = None
            if os.path.splitext(name)[1].lower() in TEXT_EXT:
                try:
                    with open(s, encoding='utf-8') as fh:
                        content = render_text(fh.read(), table, rel, errors)
                except UnicodeDecodeError:
                    content = None
            plan.append((s, os.path.join(dst, out_rel), out_rel, content))
    if errors:
        raise RenderError('\n'.join(errors))
    if fail_on_collision:
        clash = [o for _, t, o, _ in plan if os.path.exists(t) and not o.endswith('.gitkeep')]
        if clash:
            raise RenderError('collision with existing files: ' + ', '.join(sorted(clash)))
    result = {'created': [], 'replaced': [], 'kept': []}
    for s, target, out_rel, content in plan:
        exists = os.path.exists(target)
        if exists and not force:
            result['kept'].append(out_rel)
            continue
        if exists and content is not None:
            with open(target, encoding='utf-8') as fh:
                if fh.read() == content:  # identical: nothing to replace, no backup
                    result['kept'].append(out_rel)
                    continue
        result['replaced' if exists else 'created'].append(out_rel)
        if dry_run:
            continue
        os.makedirs(os.path.dirname(target), exist_ok=True)
        if exists:
            backup = os.path.join(dst, '.control-tower-backup', stamp, out_rel)
            os.makedirs(os.path.dirname(backup), exist_ok=True)
            shutil.copy2(target, backup)
        if content is None:
            shutil.copy2(s, target)
        else:
            with open(target, 'w', encoding='utf-8') as fh:
                fh.write(content)
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--src', required=True)
    ap.add_argument('--dst', required=True)
    ap.add_argument('--vocab', action='append', required=True)
    ap.add_argument('--answers', default=None)
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--force', action='store_true')
    ap.add_argument('--fail-on-collision', action='store_true',
                    help='error out if a destination file already exists (used to overlay a pack on the core)')
    args = ap.parse_args()
    answers = {}
    if args.answers:
        with open(args.answers, encoding='utf-8') as fh:
            answers = json.load(fh)
    answers.setdefault('vault_path', os.path.abspath(os.path.expanduser(args.dst)))
    try:
        table = build_table(args.vocab, answers)
        res = render_tree(args.src, args.dst, table, args.dry_run, args.force, args.fail_on_collision)
    except RenderError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(3 if 'collision' in str(exc) else 2)
    mode = 'dry run: ' if args.dry_run else ''
    if args.dry_run:
        for rel in res['created']:
            print('create  ' + rel)
        for rel in res['replaced']:
            print('replace ' + rel)
    print(f"{mode}{len(res['created'])} created, {len(res['replaced'])} replaced, {len(res['kept'])} kept (already existed)")


if __name__ == '__main__':
    main()
