# TechniView presentation run sheet

**Working limit:** 5-minute talk (300 seconds), followed by questions. Confirm the class presentation limit with the instructor. The starts below follow the current deck's speaker notes and are targets, not rehearsal results.

**Presenters:** Derek Corniello, Ryan Sippy, Jason Bellerjeau. **Timekeeper:** Jason. **Slide operator:** Derek.

The hand-offs below are short cues for the class talk. We did not use set phrases during rehearsal. On the longer slides, we each covered part of the same slide before moving on.

| Slide | Title | Planned start | Speaker | Hand-off line |
| --- | --- | --- | --- | --- |
| 1 | TechniView | 0:00 | Derek | "Here's who's working on it." |
| 2 | The Team Behind TechniView | 0:12 | Ryan | "Here's the project in brief." |
| 3 | Project Abstract | 0:27 | Jason | "Here's how people use it." |
| 4 | User Stories and System Design | 1:07 | Derek: user stories; Ryan: system flow | Within slide: "Here's how that works in the system." Next slide: "That design comes with constraints." |
| 5 | Major Project Constraints | 1:52 | Ryan | "Here's what we've built so far." |
| 6 | Project Progress | 2:17 | Jason | "Here's what comes next." |
| 7 | Expected End-of-Term Accomplishments | 2:52 | Derek | "Here's how we split the work." |
| 8 | Division of Work | 3:27 | Derek: backend and runner; Ryan: frontend; Jason: data and analytics | Within slide: "On the frontend..." then "For the data side..." Next slide: "Here's what we'll demo." |
| 9 | Expected Expo Demo | 3:52 | Derek: student workflow; Ryan: professor workflow; Jason: research | Within slide: "From the professor side..." then "For the research part..." Next slide: "Questions?" |
| 10 | Questions? | 4:55 | Derek | Invite questions and stop at 5:00. |

Slides 11–13 are backup only and have no planned speaking time. The planned 300 seconds are roughly balanced because slides 4, 8, and 9 are shared.

## Questions to prepare

| Likely question | Owner | Short answer to rehearse |
| --- | --- | --- |
| What problem does TechniView solve beyond a general coding site? | Ryan | It connects Python interview practice to course sets, assignments, and instructor feedback. |
| What is the runner, and what is go-judge? | Derek | The runner is the separate execution environment; go-judge is the program it uses to run submitted code under limits. |
| How are student submissions isolated? | Derek | Code runs on a separate runner VM with per-case CPU and memory limits. Target-VM verification remains to be shown. |
| How do you protect course data and hidden test cases? | Jason | Role and membership checks restrict access; student responses exclude hidden cases and canonical solutions. Institutional privacy review remains open. |
| Which features are implemented, and which are planned? | Derek | Show a current student and professor workflow, then name the pilot and deployment checks as planned work. Verify the exact demo before presenting. |
| What testing supports the progress slide? | Jason | Point to API, frontend, integration, and sandbox checks and the CI build; use a current run or repository evidence. |
| Can students be required to join the research study? | Jason | No. Research participation needs a separate consent process and any required IRB determination. |
| Has IRB approval been granted? | Jason | The repository does not establish that. Confirm status with the team; until then, describe the pilot as conditional. |
| What happens if the live demo fails? | Ryan | Play the prepared recording and use screenshots to walk through the same student and professor steps. |
| What are the largest remaining technical risks? | Derek | Deployed end-to-end behavior, runner capacity, privacy decisions, and accessibility still need verification. Name the next test or review for each. |

## Rehearsal log

| Date | Attendees | Total time | Derek's section(s) | Ryan's section(s) | Jason's section(s) | Changes agreed |
| --- | --- | --- | --- | --- | --- | --- |
| To schedule | Full group | Not yet measured | Not yet measured | Not yet measured | Not yet measured | Record after a timed run. |

Before presenting, add the full-group rehearsal date and approximate times here, then check the speaking split against the plan.
