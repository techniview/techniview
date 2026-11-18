# Advisor feedback: TechniView presentation

## Meeting record

- **Date and duration:** To confirm with the team.
- **Attendees:** To confirm with the team and instructor.
- **Format:** To confirm (in person, video call, or written review).
- **Deck reviewed:** `TechniView_Presentation_Draft.pptx` / `.pdf`, restored from commit `e2c0383`. Confirm this was the version reviewed before submitting the record.
- **Source of feedback:** Instructor feedback supplied by the team for this record. The prose includes the team's interpretation of the comments, so the rows below are summaries rather than verbatim quotations.

## Feedback log

The supplied feedback praised the clear introduction, logical order, coverage of system components, and division of work. It also described the slides as visually consistent. The actionable points are recorded below for revision.

| ID | Slides affected | Feedback received | Response and reason | Change to make | Owner | Status |
| --- | --- | --- | --- | --- | --- | --- |
| F-01 | 3, 4, 5, 9 | Explain the difference between the runner and go-judge for people new to the system. | Accepted. The current wording assumes technical context. | Define the runner as the isolated machine/service that invokes go-judge, then use those names consistently. | Derek | Open |
| F-02 | 3, 4, 5, 6 | Introduce technical terms and explain why each matters. | Accepted. Terms need a short explanation tied to the design. | Review first use of FastAPI, MySQL, CI, IRB, and other acronyms in slides and notes. | Ryan | Open |
| F-03 | 3, 5, 7, 9 | Distinguish the pilot study from voluntary student participation. | Accepted. The distinction affects how the research plan is understood. | Explain the proposed pilot, separate consent and participation from course activity, and avoid implying IRB clearance has been granted. | Jason | Open |
| F-04 | 3, 5, 7 | Be more explicit about protection of student information. | Accepted. Privacy is a major project constraint. | Name the relevant access controls and de-identification plan; identify institutional review and retention decisions as open. | Derek | Open |
| F-05 | 5, 6, 7, 8 | Several slides rely mainly on bullets; add useful visuals or examples. | Accepted. Concrete examples will make progress easier to assess. | Add a workflow screenshot or labeled test/progress visual where it improves the explanation. | Ryan | Open |
| F-06 | 1–10 | Make color choices serve a clear purpose. | Accepted. Visual consistency alone does not explain emphasis. | Check the accent color on each slide and reserve it for key terms or diagram paths. | Ryan | Open |
| F-07 | 4, 6, 9 | Demonstrate implemented student and professor workflows and show evidence of testing. | Accepted. The audience should see what exists now. | Prepare short workflow captures and a concise test evidence visual; separate built features from planned Expo work. | Derek, Ryan, Jason | Open |
| F-08 | 4, 5, 6, 7 | Explain why design decisions matter, not only what TechniView does. | Accepted. Link the design to constraints and requirements. | Tie the isolated runner, role checks, and research approach to their requirement or constraint IDs in narration. | Derek | Open |

## Summary of changes

This record turns the supplied feedback into eight actions with slide references and owners. The current deck has not yet been revised against these comments, so every item remains open. The next pass should focus on plain explanations of system components, accurate research language, and visible examples of implemented work. The team should compare the revised deck with this log before marking any item complete.

## Open items

| Item | Expected close date |
| --- | --- |
| Confirm meeting date, duration, attendees, format, and the exact version reviewed. | 2026-11-18 |
| Revise the deck for F-01 through F-08 and record what changed in each feedback row. | 2026-11-18 |
| Confirm any pilot, consent, and IRB statements with the team before presenting them as facts. | 2026-11-18 |
