# Assignment #7 constraints essay: TechniView

**Team:** Derek Corniello, Jason Bellerjeau, Ryan Sippy  
**Faculty advisor:** Professor William Hawkins III

This revision describes the current course-linked coding practice platform and
the planned February 15 to March 14, 2027 pilot. It replaces the earlier draft's
interview-video and transcript assumptions. The [ethics statement](Ethics_Statement.md)
gives the detailed data, security, licensing, and AI-use record.

## Economic

The team plans to host the pilot on University of Cincinnati resources rather
than pay for managed application infrastructure. That choice requires the team
to operate the application, MySQL, code runner, backups, and monitoring. The
GPU host is within campus security and VPN controls; any optional local model
for complexity estimates stays on that host. The old draft's $200-per-semester
AWS cap is not a cost estimate for this UC-hosted pilot, and the current design
does not record interview video or transcripts.

## Security

Students submit source code and receive execution results tied to their course
accounts. TechniView uses scrypt password hashes, expiring server-side sessions
with HTTP-only cookies, course role checks, and a private code runner. The
production configuration sets Secure cookies and Caddy HTTPS; the planned pilot
runs within the campus VPN. The runner executes student processes with resource
limits, seccomp, a separate network namespace, and reduced privileges on a
dedicated host. The runner container itself is privileged, so host isolation,
firewall rules, patching, and deployment checks remain necessary. UC-hosted
encrypted storage and off-host encrypted backups protect stored submissions.

## Legal

The pilot requires a UC IRB determination or approval before participant
enrollment; approval is pending. Participants sign the pilot consent form before
account creation. The team will follow applicable UC IRB requirements for
retention, de-identification, access, and any FERPA obligations that apply to
course records. The research export excludes names, emails, source code, raw
output, and timestamps, but repeated pseudonymous codes and activity patterns
can still reveal identity. The team reviews an export before sharing and removes
the link between participant codes and account identities at pilot end.

## Ethical

Participation is voluntary. Students can decline or withdraw without penalty;
withdrawal stops new activity collection but does not erase data already
collected, as the consent form explains. Participants at working sessions may
receive free food. They keep food already received if they withdraw, and they
need not finish problems to keep it. The team chose not to collect UC M-Numbers
because internal account IDs are sufficient. Students see their own progress;
authorized course staff and trained pilot team members have scoped access to
identifiable results. The team will not treat a de-identified export as risk-free:
repeated activity patterns can still make a participant recognizable.
