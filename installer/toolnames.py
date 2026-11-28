#!/usr/bin/env python3
"""The tools a user names in one free-text answer of the guided install, matched to the kit's adapters. A tool's name is
its id (a hyphen read as a space) or one of its manifest's `aliases`, matched as whole words, case aside. Standard
library only."""
import os
import re

from plan import REPO, InstallError, jload, list_packs

SEPARATOR = re.compile(r'[,;/+&\n]|\s(?:and|or|et|ou)\s', re.I)
NEGATION = re.compile(r"(?<![a-z])(?:no|not|don't|dont|never|without|pas|sans|plus de)(?![a-z])", re.I)  # "not Jira", "pas Jira"


def known_tools(packs, repo=REPO):
    """{capability: [tools]} the chosen packs ask about."""
    known = {}
    for pid in packs:
        if pid not in list_packs(repo):
            raise InstallError(f'unknown pack "{pid}" (available: {", ".join(list_packs(repo))})')
        for q in jload(os.path.join(repo, 'packs', pid, 'pack.json')).get('questions', []):
            known.setdefault(q['capability'], set()).update(t for t in q['choices'] if t != 'none')
    return {cap: sorted(tools) for cap, tools in known.items()}


def segment_start(text, at):
    """Where the part of `text` that holds position `at` starts (parts are cut at SEPARATOR)."""
    return max([m.end() for m in SEPARATOR.finditer(text, 0, at)] or [0])


def named_tools(text, known, repo=REPO):
    """(spans, {capability: {tools}}, {capability: {tools}}): the known tools named in `text`, and those right after a
    negation in the same part ("not Jira", but not Linear in "not Jira but Linear"), which are left out. A longer name
    takes its words from a shorter one: "github issues" is not also "github"."""
    found = []
    for cap, tools in known.items():
        for tool in tools:
            for name in {tool, tool.replace('-', ' '), *jload(os.path.join(repo, 'adapters', cap, tool + '.json')).get('aliases', [])}:
                found += [(m.start(), m.end(), cap, tool) for m in re.finditer(rf'(?<![a-z0-9]){re.escape(name)}(?![a-z0-9])', text, re.I)]
    accepted = []
    for start, end, cap, tool in sorted(found, key=lambda f: f[0] - f[1]):  # longest first
        if all(end <= s or start >= e for s, e, _, _ in accepted):
            accepted.append((start, end, cap, tool))
    spans, named, excluded, previous = [], {}, {}, 0
    for start, end, cap, tool in sorted(accepted):  # in text order: a negation reaches the next tool only
        negated = NEGATION.search(text, max(segment_start(text, start), previous), start)
        (excluded if negated else named).setdefault(cap, set()).add(tool)
        spans.append((start, end))
        previous = end
    return spans, named, excluded


def unknown_parts(text, spans):
    """The parts of `text` that name no known tool and say no tool is not used ("no Slack"), cut at punctuation and at
    "and", "or", "et", "ou"."""
    bounds = [0] + [x for m in SEPARATOR.finditer(text) for x in (m.start(), m.end())] + [len(text)]
    return [text[a:b].strip() for a, b in zip(bounds[::2], bounds[1::2])
            if text[a:b].strip() and not NEGATION.search(text[a:b]) and not any(s < b and e > a for s, e in spans)]


def match_tools(text, packs, repo=REPO):
    """For the capabilities the chosen packs ask about: the tool named for each (`none` when none is), the capabilities
    with two tools named (a conflict, never guessed), the tools named after a negation (left out), and the parts of the
    answer that name no known tool."""
    known = known_tools(packs, repo)
    spans, named, excluded = named_tools(text, known, repo)
    return {'tools': {cap: next(iter(named.get(cap, ())), 'none') for cap in known if len(named.get(cap, ())) < 2},
            'conflicts': {cap: sorted(t) for cap, t in named.items() if len(t) > 1},
            'excluded': {cap: sorted(t) for cap, t in excluded.items()}, 'unknown': unknown_parts(text, spans)}
