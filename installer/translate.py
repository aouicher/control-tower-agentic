#!/usr/bin/env python3
"""The vault in the user's language: the visible text of its notes, templates and dashboards, cut into segments (a heading,
a table cell, a list item, a line of prose, a dashboard label), translated once by Claude at install, checked, and kept in
the vault (.control-tower/translation.json). The installer puts it back every time it writes those files, so updates keep
it. Links, tokens, tags, handles, code, queries, properties, folder names and Claude's own instructions (skills, CLAUDE.md)
stay as they are. Standard library only."""
import json
import os
import re

from plan import InstallError, jload

PROTECTED = re.compile(r'!?\[\[[^\]]*\]\]|\{\{[^}]*\}\}|`[^`]*`|https?://\S+|(?<![\w/])[#@][\w/-]+')
LETTER = re.compile(r'[^\W\d_]')
NAMED = re.compile(r'`(#{1,6}\s+[^`\n]+)`')  # a heading as a skill or a report names it
HEADING = re.compile(r'^(#{1,6}\s+(?:[^\w\s#]+\s+)?)(.+?)\s*$')  # the icon in front stays
TABLE_RULE = re.compile(r'^\s*\|?\s*:?-{2,}')
PREFIX = re.compile(r'^(\s*(?:>\s*(?:\[![\w-]+\][-+]?\s*)?)?(?:(?:[-*+]|\d+\.)\s+(?:\[[ xX]\]\s+)?)?)(.*)$')
LABEL = re.compile(r'^(\s*(?:-\s+)?(?:displayName|name):\s*)(.+?)\s*$')  # a dashboard's column and view names
STRUCTURE = re.compile(r'^\s*(#|>|\||[-*+]\s|\d+\.\s|---|```|~~~)')
MARKS = ('|', '`', '](', '<', '>', '%%')  # a cell, code, a link, HTML or a comment: never more than the English text has
MAX_TEXTS, MAX_BYTES = 5000, 1 << 20


def translatable(rel):
    rel = rel.replace(os.sep, '/')
    return rel.endswith(('.md', '.base')) and rel != 'CLAUDE.md' and not rel.startswith(('.claude/', '.obsidian/', '.control-tower/'))


def has_words(text):
    return bool(LETTER.search(PROTECTED.sub('', text)))


def cell_bounds(line):
    """Where the cells of a table row start and end: at each `|` outside a link, a token or code."""
    hidden = PROTECTED.sub(lambda m: '\0' * len(m.group(0)), line)
    cuts = [-1] + [i for i, c in enumerate(hidden) if c == '|'] + [len(line)]
    return [(a + 1, b) for a, b in zip(cuts, cuts[1:])]


def named_headings(texts):
    """The headings the kit's skills, rules and reports name (`## ✅ Tasks`): they stay as they are, so they find them. The
    user's own skills are written later, from the vault as it is."""
    return {m.group(2) for text in texts for h in NAMED.findall(text) for m in [HEADING.match(h)] if m}


def line_spans(line, keep):
    """(start, end) of the segments of one Markdown line; a heading in `keep` has none."""
    if line.lstrip().startswith(('![[', '<!--', '%%')) or TABLE_RULE.match(line):
        return []
    m = HEADING.match(line)
    if m:
        return [m.span(2)] if has_words(m.group(2)) and m.group(2) not in keep else []
    if line.lstrip().startswith('|'):
        out = []
        for a, b in cell_bounds(line):
            s, e = a + len(line[a:b]) - len(line[a:b].lstrip()), a + len(line[a:b].rstrip())
            if e > s and has_words(line[s:e]):
                out.append((s, e))
        return out
    m = PREFIX.match(line)
    text = m.group(2).rstrip()
    return [(m.start(2), m.start(2) + len(text))] if has_words(text) else []


def unquote(value):
    """A dashboard label as YAML reads it: the kit's are plain or double-quoted (a JSON string)."""
    try:
        return json.loads(value) if len(value) > 1 and value[0] == value[-1] == '"' else value
    except ValueError:
        return value


def spans(rel, text, keep=frozenset()):
    """(lines, [(line, start, end, segment)]): the segments of a file, outside a note's frontmatter and fenced code."""
    lines, out = text.split('\n'), []
    if not translatable(rel):
        return lines, out
    if rel.endswith('.base'):
        for i, line in enumerate(lines):
            m = LABEL.match(line)
            if m and has_words(unquote(m.group(2))):
                out.append((i, m.start(2), m.end(2), unquote(m.group(2))))
        return lines, out
    front, fence = lines[:1] == ['---'], ''
    for i, line in enumerate(lines):
        mark = line.lstrip()[:3]
        if front:
            front = not (i > 0 and line.strip() == '---')
        elif mark in ('```', '~~~') and fence in ('', mark):  # a fence closes only with its own mark
            fence = '' if fence else mark
        elif not fence:
            out += [(i, s, e, line[s:e]) for s, e in line_spans(line, keep)]
    return lines, out


def segments(rel, text, keep=frozenset()):
    return [seg for _, _, _, seg in spans(rel, text, keep)[1]]


def apply(rel, text, mapping, keep=frozenset()):
    """The file with each segment the translation has replaced; a dashboard label is quoted, so it stays valid YAML."""
    lines, found = spans(rel, text, keep)
    for i, s, e, seg in reversed(found):  # right to left: earlier offsets on the line stay right
        if seg in mapping:
            new = json.dumps(mapping[seg], ensure_ascii=False) if rel.endswith('.base') else mapping[seg]
            lines[i] = lines[i][:s] + new + lines[i][e:]
    return '\n'.join(lines)


def problems(mapping):
    """Why a translation is refused. It changes words only: one line each, no longer than needed, the same links, tokens,
    tags, handles and code, and no table cell, heading, quote, list, code, link, HTML or comment made out of plain text."""
    if not isinstance(mapping, dict) or len(mapping) > MAX_TEXTS:
        return [f'a translation is an object of at most {MAX_TEXTS} texts: {{"English text": "translated text"}}']
    out = []
    for k, v in mapping.items():
        if not isinstance(k, str) or not isinstance(v, str) or not v.strip():
            out.append(f'"{str(k)[:40]}": a text and its translation')
        elif any(ord(c) < 32 or 0x7f <= ord(c) <= 0x9f or 0xd800 <= ord(c) <= 0xdfff for c in v) or len(v) > 3 * len(k) + 60:
            out.append(f'"{k[:40]}": its translation is one line, about as long')
        elif sorted(PROTECTED.findall(k)) != sorted(PROTECTED.findall(v)):
            out.append(f'"{k[:40]}": links, tokens, tags and code stay exactly as they are')
        elif any(PROTECTED.sub('', v).count(m) > PROTECTED.sub('', k).count(m) for m in MARKS) or bool(STRUCTURE.match(v)) > bool(STRUCTURE.match(k)):
            out.append(f'"{k[:40]}": a translation adds no table cell, heading, quote, list, code, link, HTML or comment')
    return out[:20]


def checked(mapping, where):
    why = problems(mapping)
    if why:
        raise InstallError(f'translation in {where} refused: ' + '; '.join(why))
    return mapping


def load(vault, language, extra_file=None):
    """The vault's translation for its language, with the texts of `extra_file` added (both checked). A translation into
    another language than the answers' is not used, and stays on disk until a translation into the new one replaces it:
    the vault is written in English until its texts are translated again."""
    path = os.path.join(vault, '.control-tower', 'translation.json')
    try:
        if any(f and os.path.isfile(f) and os.path.getsize(f) > MAX_BYTES for f in (path, extra_file)):
            raise ValueError(f'more than {MAX_BYTES} bytes')
        kept = jload(path, {})
        new = checked(jload(extra_file), extra_file) if extra_file else {}
    except (OSError, ValueError) as exc:
        raise InstallError(f'the translation cannot be read: {exc}')
    texts = checked(kept.get('texts', {}), path) if isinstance(kept, dict) and kept.get('language') == language else {}
    return {**texts, **new}

