# Courses, enrollment, and account email

Instructors can create courses with `POST /api/courses`, replace course metadata
with `PUT /api/courses/{id}`, and archive with `POST /api/courses/{id}/archive`.
Creation accepts `name`, optional `description`, and an IANA `timezone` (default
`UTC`). Creation returns the course and its raw `join_token` once. The database
stores the token hash. `POST /api/courses/{id}/join-link` replaces the shared token
and invalidates the old link. Archived courses remain readable and reject writes.

Removing a member sets `withdrawn_at`. Their submissions, recipient snapshots,
progress, and authored assignments remain. Shared join links can reactivate a
withdrawn member without changing their role. The last instructor cannot withdraw
or be demoted.

## CSV roster import

Send `POST /api/courses/{id}/enrollments/import` with a JSON `csv` string:

```json
{"csv":"name,email\nAlex Student,alex@example.com\n"}
```

The CSV must have exactly `name,email` headers and at most 2,000 rows. The API
normalizes email case and rejects duplicate emails, malformed rows, disabled
accounts, and staff accounts. An invalid row rejects the whole import.

Verified existing students join immediately. New or unverified students receive
a pending roster entry and an email with a link restricted to their email address.
Importing the same pending entry again updates its name without sending another
email. Newly enrolled existing students receive a course notification.
`GET /api/courses/{id}/enrollments` lists pending entries for staff;
`DELETE /api/courses/{id}/enrollments/{enrollment_id}` cancels one, invalidating
its link and pending verification tokens for that course.

## Signup and password recovery

`POST /api/join/{token}/signup` returns 202 and queues verification email.
It creates an unverified account, without a session or course membership.
`POST /api/auth/verify-email` accepts `{"token":"..."}`, verifies the email,
and enrolls the account in the token's active course. The user then logs in.
A join login for an unverified account returns 202 and queues verification again,
subject to the token cooldown. Already verified accounts retain the usual join
login flow. Existing accounts are marked verified by the migration.

`POST /api/auth/password-recovery` accepts `{"email":"..."}` and returns the
same 202 response for known and unknown accounts. `POST /api/auth/password-reset`
accepts `token`, `password`, and `password_confirm`; it consumes all outstanding
reset tokens for the account and revokes every existing session. Verification and
reset tokens expire and can be consumed once. Signup/join requests and recovery
requests each have a database-backed limit of 30 requests per source IP per hour.
Issuing another token for the same account, purpose, and course also observes
`EMAIL_TOKEN_COOLDOWN_SECONDS`. Run behind a trusted proxy configuration so the
application receives the actual source address.

## Delivery configuration

The application worker drains `email_jobs`. Requests only create jobs; they do not
contact Resend. A worker claims a job with a lease, commits, delivers outside the
transaction, then records the result if it still owns the lease. Failed deliveries
retry after 30, 60, 120, then 240 seconds with the default five-attempt limit.
Expired worker claims can be reclaimed. Resend requests use a stable idempotency
key for each job. Exhausted jobs retain their failure class in `last_error` for
inspection; provider response bodies and credentials are never stored there.

Configure these settings in both the API and worker:

- `EMAIL_DELIVERY_MODE`: `disabled`, `capture`, or `resend`.
- `EMAIL_SIGNING_KEY`: a secret of at least 32 characters. Keep it stable across
  API and worker restarts. Tokens in queued emails are reconstructed with HMAC;
  the database holds token hashes and nonces, never raw token strings.
- `PUBLIC_APP_URL`: browser origin used to construct email links.
- `EMAIL_FROM` and `RESEND_API_KEY`: the verified sender and API key for Resend.
- `PASSWORD_RESET_MINUTES` and `EMAIL_VERIFICATION_MINUTES`: token lifetimes.
- `EMAIL_MAX_ATTEMPTS` and `EMAIL_LEASE_SECONDS`: delivery retry and lease limits.

For local development, use `capture` and `EMAIL_CAPTURE_DIR`. Delivery writes one
JSON email file per job, with owner-only permissions. These files contain working
links, so keep them local and remove them after use. Capture mode performs no
network delivery. The default disabled mode rejects new signup, CSV imports, and
recovery requests that need email configuration.

Email links use frontend routes `/verify-email?token=...`,
`/reset-password?token=...`, and `/join/{token}`. The first two routes must submit
the token to their API endpoints; opening a link alone never changes account state.
