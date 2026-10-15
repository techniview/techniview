# Backend reporting

`GET /api/me/analytics` accepts `scope=all|practice|assignments`, `course_id`,
`assignment_id`, `difficulty`, `tag`, `limit` (1-100), and `offset`. Course and
assignment filters select coursework only. The response keeps the overall
`metrics` and includes paginated per-problem `items`; totals cover all matching
rows, not just the page. A problem assigned more than once contributes once per
assignment to the metrics. Practice contributes one progress record per problem.

Course instructors can download these reports. Grade exports accept an optional
`assignment_id`; research exports require `assignment_id` and `publication_key`:

- `/api/courses/{course_id}/exports/grades.csv` includes every current recipient
  and item in published or archived assignments, including students who withdrew
  and students who have not started. An explicit recipient removal excludes that
  student from the current export and course summary; the audit and submissions
  remain. Scores use eligible attempts, including approved late work.
- `/api/courses/{course_id}/exports/research.csv` includes assignment submission
  outcomes. It excludes names, emails, source code, execution output, exception
  text, test data, timestamps, and submission IDs. Participants receive stable
  HMAC identifiers scoped to the course and publication key. Problem and assignment
  contexts also use pseudonyms, with no operational IDs exported. Timings are seconds
  since the participant's first attempt in the selected assignment, plus processing
  duration. These are pseudonyms, not a guarantee
  against identification through knowledge of a student's outcomes.

Set `RESEARCH_EXPORT_SECRET` to a random secret of at least 32 bytes in the backend
process environment. Keep it stable for longitudinal exports. Rotating it changes
all participant identifiers. Research exports return 503 until it is configured.
Neither report includes unassigned practice activity. Spreadsheet formula prefixes
in text cells are escaped.

## Rebuild progress

Course analytics read maintained summary totals; medians come from progress rows.
Summary updates share the mutation transaction. To reconstruct progress counters,
grades, exception counts, and course summaries from submissions, stop
all API and submission worker processes, then run from the repository root:

```
PYTHONPATH=backend uv run python -m app.services.rebuild_progress
```

The command runs in one transaction. It preserves recorded first-open times,
creates missing progress rows using the earliest submission time, clears derived
counters, and replays completed submissions. Infrastructure errors and unfinished
submissions do not count as attempts. Unapproved late work counts as an attempt
but does not earn credit. Repeating the command produces the same result. Restart
the API and workers after it completes. Keep a database backup before maintenance.
