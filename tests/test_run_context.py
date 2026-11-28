"""Jobs take their dates from a `## Run context` block the runner writes into the prompt, never from the `date` command,
and list vault folders with Glob, never `ls`."""
import datetime
import glob
import os
import re
import sys
import unittest
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scheduler'))
import run_job  # noqa: E402

PARIS = ZoneInfo('Europe/Paris')
RULE = run_job.RUN_CONTEXT_RULE
# a date or ls COMMAND, not the frontmatter key `date` (`date: YYYY-MM-DD`, `date` (today)): `date +%F`, `date "+..."`,
# `date -v-7d`, "with `date`", "from `date`", "run date", `ls ...`, "with one ls"
DATE_OR_LS = re.compile(r'`date [+\-"\']|(?<!not )(?<!never )\b(with|from) `date`|(?<!not )(?<!never )\brun `?(date|ls)\b'
                        r'|`ls [^`]|\bwith one `?ls\b')


def shipped(pattern):
    return sorted(glob.glob(os.path.join(ROOT, pattern), recursive=True))


def context(*args, tz=PARIS):
    return run_job.run_context(datetime.datetime(*args, tzinfo=tz))


class RunContextTests(unittest.TestCase):
    def test_a_monday(self):
        c = context(2026, 11, 23, 8, 5)
        self.assertIn('- Now: 2026-11-23 08:05 (23/11/2026 at 08:05), Monday, Europe/Paris', c)
        self.assertIn('- Today: 2026-11-23', c)
        self.assertIn('- Year: 2026', c)
        self.assertIn('- ISO week: 2026-W48, Monday 2026-11-23 to Sunday 2026-11-29', c)
        self.assertIn('- Last complete ISO week: 2026-W47, Monday 2026-11-16 to Sunday 2026-11-22', c)
        self.assertIn('- The week before: 2026-W46, Monday 2026-11-09 to Sunday 2026-11-15', c)
        self.assertIn('- Previous working day: 2026-11-20, Friday', c)
        self.assertIn('- Unix time (epoch seconds, for tools that take one): now 1795417500, today 00:00 1795388400, previous working day 00:00 1795129200', c)
        self.assertTrue(c.startswith('## Run context\n'))
        self.assertIn('do not run `date`', c)

    def test_unix_times_follow_the_clock_change(self):
        c = context(2026, 3, 30, 8, 0)  # the clocks moved forward on Sunday 29 March: Friday midnight is 71 hours before Monday's
        self.assertIn('now 1774850400, today 00:00 1774821600, previous working day 00:00 1774566000', c)

    def test_a_sunday_is_still_in_its_own_iso_week(self):
        c = context(2026, 11, 29, 23, 59)
        self.assertIn('- ISO week: 2026-W48, Monday 2026-11-23 to Sunday 2026-11-29', c)
        self.assertIn('- Last complete ISO week: 2026-W47', c)
        self.assertIn('- Previous working day: 2026-11-27, Friday', c)

    def test_first_of_january_in_iso_week_53(self):
        c = context(2021, 1, 1, 9, 0)  # a Friday that belongs to 2020-W53
        self.assertIn('- Year: 2021', c)
        self.assertIn('- ISO week: 2020-W53, Monday 2020-12-28 to Sunday 2021-01-03', c)
        self.assertIn('- Last complete ISO week: 2020-W52, Monday 2020-12-21 to Sunday 2020-12-27', c)
        self.assertIn('- Previous working day: 2020-12-31, Thursday', c)

    def test_daylight_saving_days_in_paris(self):
        utc = datetime.timezone.utc
        spring = run_job.run_context(datetime.datetime(2026, 3, 29, 1, 30, tzinfo=utc).astimezone(PARIS))
        self.assertIn('- Now: 2026-03-29 03:30 (29/03/2026 at 03:30), Sunday, Europe/Paris', spring)
        autumn = run_job.run_context(datetime.datetime(2026, 10, 25, 1, 30, tzinfo=utc).astimezone(PARIS))
        self.assertIn('- Now: 2026-10-25 02:30 (25/10/2026 at 02:30), Sunday, Europe/Paris', autumn)

    def test_now_in_the_installed_timezone(self):
        when = run_job.now_in('Asia/Tokyo')
        self.assertEqual(str(when.tzinfo), 'Asia/Tokyo')
        self.assertEqual(run_job.now_in('Not/A_Zone').utcoffset(), datetime.timedelta(0), 'an unknown zone falls back to UTC')
        self.assertIn(', UTC\n', run_job.run_context(run_job.now_in('')), 'so does a missing one')


class NoDateOrLsInJobsTests(unittest.TestCase):
    def test_the_pattern_finds_commands_not_the_frontmatter_key(self):
        for text in ('Get it with `date +%F`.', 'with `date "+%d/%m"`', '(on macOS `date -v-7d`)', 'Compute the dates with `date`.',
                     '(real time from `date`)', 'List notes with one `ls` per folder', 'run `ls work/`'):
            self.assertRegex(text, DATE_OR_LS)
        for text in ('`date: YYYY-MM-DD` (today)', 'frontmatter `title`, `date` (today, `YYYY-MM-DD`)', 'the `date` property',
                     'update the frontmatter `date`', '`publish_date` before today', RULE, 'never run `date` or `ls`',
                     'sorted by date', 'the `ls` command is never needed'):
            self.assertNotRegex(text, DATE_OR_LS)

    def test_no_job_prompt_runs_date_or_ls(self):
        prompts = shipped('packs/*/jobs/*/prompt.md.tmpl') + shipped('core/jobs/*/prompt.md.tmpl')
        self.assertGreaterEqual(len(prompts), 10)
        for path in prompts:
            for n, line in enumerate(open(path, encoding='utf-8'), 1):
                with self.subTest(prompt=os.path.relpath(path, ROOT), line=n):
                    self.assertNotRegex(line, DATE_OR_LS)

    def test_every_skill_that_runs_date_says_to_use_the_run_context_first(self):
        found = 0
        for path in shipped('core/vault/.claude/skills/*/SKILL.md') + shipped('packs/*/vault/.claude/skills/*/SKILL.md*'):
            text = open(path, encoding='utf-8').read()
            m = DATE_OR_LS.search(text)
            if not m:
                continue
            found += 1
            with self.subTest(skill=os.path.relpath(path, ROOT)):
                self.assertIn(RULE, text)
                self.assertLess(text.index(RULE), m.start(), 'the rule comes before the first date command')
        self.assertGreaterEqual(found, 10)

    def test_a_skill_named_by_a_job_prompt_follows_the_rule(self):
        named = 0
        for path in shipped('packs/*/jobs/*/prompt.md.tmpl') + shipped('core/jobs/*/prompt.md.tmpl'):
            for skill in re.findall(r'\.claude/skills/([a-z0-9-]+)/SKILL\.md', open(path, encoding='utf-8').read()):
                files = shipped(f'core/vault/.claude/skills/{skill}/SKILL.md*') + shipped(f'packs/*/vault/.claude/skills/{skill}/SKILL.md*')
                with self.subTest(prompt=os.path.relpath(path, ROOT), skill=skill):
                    self.assertTrue(files, 'the skill exists')
                    for f in files:
                        text = open(f, encoding='utf-8').read()
                        m = DATE_OR_LS.search(text)
                        self.assertTrue(m is None or (RULE in text and text.index(RULE) < m.start()))
                named += 1
        self.assertGreaterEqual(named, 2)


if __name__ == '__main__':
    unittest.main()
