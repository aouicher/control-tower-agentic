#!/usr/bin/env python3
"""Render a template tree into a destination, replacing {{ct.*}} tokens.

Standard library only (Python 3.9+). Idempotent and safe by default:
  * existing destination files are never overwritten unless --force is given;
    with --force the old file is first copied to <dst>/.control-tower-backup/<timestamp>/
  * Obsidian placeholders such as {{title}} and {{date:YYYY-MM-DD}} are left untouched
  * an unknown {{ct.xxx}} token is an error (nothing is written)
  * files ending in .tmpl lose that suffix (CLAUDE.md.tmpl -> CLAUDE.md)

Tokens:
  {{ct.team}} {{ct.teams}} {{ct.Team}} {{ct.Teams}}      (same for workstream, risk, person/people)
  {{ct.owner_name}} {{ct.owner_handle}} {{ct.timezone}} {{ct.vault_path}} {{ct.language}}   (from the answers)

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
SCALARS = ('owner_name', 'owner_handle', 'timezone', 'vault_path', 'language')
DEFAULTS = {'language': 'English'}  # an answers file may leave it out
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
        # article-aware singular: {{ct.a_workstream}} -> "an initiative" / "a campaign"; {{ct.A_workstream}} at a sentence start
        article = forms.get('article') or ('an' if forms['singular'][:1].lower() in 'aeiou' else 'a')
        table['a_' + key] = f"{article} {forms['singular']}"
        table['A_' + key] = f"{article.capitalize()} {forms['singular']}"
    for key in SCALARS:
        if key in answers or key in DEFAULTS:
            table[key] = str(answers.get(key, DEFAULTS.get(key)))
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


def update_action(target, out_rel, content, src, installed):
    """What an update does with one kit file: create, kept (already identical), updated, stashed or skipped."""
    if not os.path.exists(target):
        return 'skipped' if out_rel in installed else 'create'
    new = (content.encode('utf-8') if content is not None else open(src, 'rb').read())
    current = open(target, 'rb').read()
    if current == new:
        return 'kept'
    if installed.get(out_rel) and hashlib.sha256(current).hexdigest() == installed[out_rel]:
        return 'updated'
    return 'stashed'


def render_tree(src, dst, table, dry_run=False, force=False, fail_on_collision=False, rename=None, installed=None, stash_dir=None, skip=None):
    """Render src into dst. Returns {'created': [...], 'replaced': [...], 'kept': [...]} (relative paths).

    `rename` is an optional function(relative_output_path) -> relative_output_path, used by the installer
    to place files (for example prompt.md.tmpl -> prompt.md).

    Update mode (`installed` = {relative path: sha256 at install time}, from the vault manifest):
      * a file the user never edited (same checksum as installed) is replaced by the new version -> 'updated';
      * a file the user edited is kept; the new version is written under `stash_dir` for a manual merge -> 'stashed';
      * a file that was installed and then deleted by the user is not recreated -> 'skipped'.
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
            if skip and skip(out_rel):  # replaced by a private pack, or excluded
                continue
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
    result = {'created': [], 'replaced': [], 'kept': [], 'updated': [], 'stashed': [], 'skipped': []}
    for s, target, out_rel, content in plan:
        exists = os.path.exists(target)
        if installed is not None and not force:
            action = update_action(target, out_rel, content, s, installed)
            if action != 'create':
                result[action].append(out_rel)
                if dry_run or action in ('kept', 'skipped'):
                    continue
                dest = target if action == 'updated' else os.path.join(stash_dir, out_rel)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                if content is None:
                    shutil.copy2(s, dest)
                else:
                    with open(dest, 'w', encoding='utf-8') as fh:
                        fh.write(content)
                continue
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
