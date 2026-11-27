# What your jobs may do

Your scheduled jobs run alone, often at night, with nobody watching. So they start with very little: they read your vault and write their reports in it, and that is all. Anything more (a company tool, a connection such as Slack or Jira, a web site) is only possible after **you** say yes to it.

You never edit a file to give access. You answer questions, and the kit does the rest.

## When you install

The installer shows what each job would use, in plain words, for example:

> morning-prs: commands: gh pr list, gh pr view; web sites: api.github.com

The guided installer (`/install-control-tower`) asks you one question: "Do you allow these jobs to use this?". Say no for a job, and that job is simply not installed. You can add it later by running the installer again.

## My job is blocked: what do I do?

A job that needed something it was not allowed to use writes a weaker report, or says so in its log (`denied: 2`). To fix it:

1. Open Claude Code in your vault.
2. Type `/job-permissions` (or just say "my job is blocked").
3. Claude explains each thing the job was refused, one at a time, and asks "Allow" or "Not now".
4. For each "Allow", the job gets that access from its next run. Claude offers to run the job again right away to check.

To take an access back, ask the same skill ("stop letting the morning job read Slack").

## What can never be allowed

Some things are refused for every job, even if you say yes. A job runs without you, so a mistake, or a sneaky instruction hidden in a web page or a ticket it reads, must not be able to do damage:

| Never allowed | Why |
|---|---|
| Writing files outside the vault, or changing the vault's rules, templates and settings | A job could break your setup or change what the next job does. |
| Running any program it likes: shells, Python, Node, scripts, `curl`, `ssh`, copying or deleting files with shell commands | That would be the same as giving it your whole computer. |
| Reading files with a command (`cat`, `ls`, `grep`, `head`, `date`...) | Jobs read your notes with Claude's own file tools, which cannot leave the vault, and get the date from the kit. |
| Sending, posting, creating, updating or deleting anything through a connection (send a message, create a ticket, comment, merge, deploy...) | Jobs only read. Writing on your behalf is for you, in a normal Claude session. |
| A whole connection or "everything" at once, searching the whole web | Access is given one command, one tool or one web site at a time, so you know exactly what you said yes to. |
| Git commands that change history (commit, push, reset...) | Jobs read history only. |
| Reading your passwords, keys and tokens (`.ssh`, `.aws`, `.env` files...) | Even if a job is tricked, your secrets stay out of reach. |

A safety guard also checks every action while the job runs and stops the ones above, whatever the job's settings say. When it does, `/job-permissions` tells you what was stopped and why, and does not offer to allow it.

One limit, without strict mode: the guard checks every file read and write, but a command you allowed is checked only against a list of known dangerous patterns. A command with an option that writes a file (for example `sort -o`) could therefore write outside the vault. Strict mode (below) closes this: the sandbox lets commands write only in the vault, never in its settings or git files. So allow commands only from tools you know, or use strict mode.

## Strict mode (optional)

For extra protection, ask for **strict mode** when you install (the answers key `"strict": true`). Every command a job runs is then closed in a sandbox provided by Claude Code: it cannot read your keys folders (`~/.ssh`, `~/.aws`...), cannot write to the vault's settings, and can only reach the web sites the job declared. If the sandbox is not available on the computer, the job refuses to run instead of running unprotected.

On Linux, strict mode needs two small programs, `bubblewrap` and `socat` (the health check, `installer/doctor.py`, tells you if they are missing). On macOS nothing needs to be installed.

## For pack authors

How a pack declares what its jobs need (`permissions.allow`, `network`, `sandbox_allow_write`) is in [private packs](private-packs.md#job-permissions).
