---
name: job-permissions
description: Explain why a scheduled job was blocked and let the user allow what it needs by answering questions, never by editing a file. Use when the user says /job-permissions, "my job is blocked", "why did my job fail", "the report is empty", "allow my job to ...", or asks what a job may use.
argument-hint: "[job id, optional]"
---

# Job permissions

Scheduled jobs run alone, so they only use what was allowed for them. When a job needs something more (a company tool, a connection, a web site), it is refused and the refusal is recorded. This skill explains each refusal in plain words and asks the user, one question at a time, whether to allow it. Nothing is allowed without a clear "yes". Many users are not developers: no jargon.

## Ground rules

- Never edit a file by hand, not even `.control-tower/answers.json` or a `settings.json`. Every change goes through `installer/permissions.py`.
- Never ask for, accept or write a password, token or key.
- Say what a permission lets the job do, never the rule itself: "read your Slack messages", not `Bash(slackcli ...)`; "look up tickets in Jira", not `Bash(twg jira:*)`. Show the rule only if the user asks for it.
- Talk in the user's language.

## Steps

1. Read `.control-tower/manifest.json` in this vault: `repo` is the folder of the control tower kit, `ct_home` is the runtime folder. If the file or `repo` is missing, say that this vault was installed by an older version of the kit and that running the installer again (`--update`) fixes it, then stop.
2. Run `python3 <repo>/installer/permissions.py list --ct-home <ct_home> --vault <this vault>`. It prints JSON: a `denials` list, each with `job`, `explain`, `allow_means`, `rule`, `verdict` (`can-allow` or `never`), `why` and `granted`. With an argument, keep only that job.
3. If the list is empty, say that no job was refused during its latest run. If a job still fails, suggest reading `<ct_home>/logs/<job>.log`, and stop.
4. Skip items with `granted: true`: they are already allowed, the job will use them from its next run. Say so in one line.
5. For each `never` item, explain in one sentence what the job tried to do and why it can never be allowed (from `why`: for example "jobs never send messages for you" or "this would let a job run any program"). Do not offer to allow it. If the job cannot do its work without it, say the job's instructions may need a change, by whoever wrote that job.
6. For each `can-allow` item, ask one question, with the options "Allow" and "Not now":
   "The job <job name> tried to <allow_means, in plain words>. Allow it from now on?"
   Mention what this lets the job do every time it runs, in one short sentence (for example: "It can then read your Jira tickets; it cannot change them.") only when you are sure of it.
7. For each "Allow", run `python3 <repo>/installer/permissions.py grant --vault <this vault> --job <job> --rule "<rule>"` and relay its one-line result. If it fails, show the message in plain words and do not retry more than once. For "Not now", do nothing.
8. If at least one permission was allowed, ask whether to run the job again now to check it. On yes, run `python3 <ct_home>/bin/run_job.py --job <job> --ct-home <ct_home>` (it can take a few minutes), then run step 2 again for that job and report: the job worked, or what it was still refused.
9. To take a permission back, the user can ask for it: run the same command with `revoke` instead of `grant`, after a clear yes.

More: the kit's `docs/permissions.md`.
