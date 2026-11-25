---
name: research
description: Research a topic, searching the vault first and then the web, and save a sourced note in library/. Use when the user says /research <topic>, "research X and save it", "add X to my vault" or "what do we know about X".
argument-hint: "<topic>"
---

# Research

## Steps

1. Search the vault first: `grep -ril "<keywords>" . --include=*.md --exclude-dir=_system --exclude-dir=.obsidian`. Read the relevant hits and tell the user what they already have.
2. Search the web for what is missing, if a web search tool is available; otherwise say so and work from the vault only. Prefer primary sources (official documentation, standards, regulators, papers, vendor docs) over blogs. Never send confidential vault content to external services: search with generic keywords.
3. If a note on the topic already exists in `library/`, update it (append a dated section) instead of creating a duplicate.
4. Otherwise write `library/<descriptive-hyphenated-title>.md` from `_system/templates/resource.md`:
   - frontmatter: `title` (double-quoted), today's `date`, `type: resource`, `status: draft`, 2 to 4 lowercase hyphenated `tags`;
   - sections described under Presentation;
   - wikilinks only to notes that exist.
5. Paraphrase sources, never paste long passages.
6. Reply with the file path and a 3-line summary. Anything that should become a task is proposed to the user, and if written it carries `#to-triage`.

## Presentation

Follow section 6 (page style) of the vault `CLAUDE.md`, using `_system/templates/resource.md`:
- `> [!summary] Summary`: 3 bullets, answer first;
- `## 📊 Key concepts`: table `| Concept | In plain words | Why it matters |`;
- `## 🔗 Connections`: wikilinks to existing vault notes found in step 1;
- `## 📎 Sources`: in a folded callout `> [!note]- Sources`, title and URL for each source used, every line prefixed with `> `.
