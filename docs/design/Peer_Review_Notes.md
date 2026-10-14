# TechniView peer design review notes

## Review summary

Overall, this was easy to follow. I liked how the D0, D1, and D2 views fit together, and the grading diagram makes the Judge0 failure paths clear. The requirements table also looks useful for Week 9. The first review pass caught a Markdown separator issue in that table, and the 56 edge-case rows felt long. The separator is fixed, and the table now has 12 grouped scenarios focused on the main risks.

I did not find a reason to hold up the design. I noted a few small things the team can check as implementation gets underway.

## Feedback and follow-up actions

| ID | Rubric criterion | Feedback and reviewer | Action | Owner | Priority | Due date |
|---|---|---|---|---|---|---|
| PR-01 | Clarity | The D0-to-D2 progression is clear. The note about the two D0 database cylinders being logical groups helped me understand how the diagram matches the current setup. Raised in peer review. | Keep that note beside the D0 conventions when the diagram is reused in later project documents. | Derek Corniello | worth considering | Week 9 technical specification |
| PR-02 | Completeness | D2 fills in route and model details that were not in the older D1 snapshot. The snapshot label made the difference easy to understand. Raised in peer review. | Carry the current route list into the technical specification and update it if routes change. | Jason Bellerjeau | worth considering | Week 9 technical specification |
| PR-03 | Feasibility | The grading failure path is helpful. It made the runner boundary and fallback behavior easier to talk about. Raised in peer review. | Check the timeout and retry limits against the deployed Judge0 configuration during implementation planning. | Derek Corniello | worth considering | Week 9 technical specification |
| PR-04 | Risk | SippyR suggested trimming the 56 edge-case rows to a shorter set of about 10 to 15. | Group overlapping component cases into 12 scenarios while keeping boundary, timing/concurrency, bad-input, and dependency risks visible. | Derek Corniello | worth considering | Week 8 submission |
| PR-05 | Completeness | I liked that the requirements table points to specific design details and checks for scope in reverse too. Raised in peer review. | Use the table as the starting traceability matrix for the Week 9 technical specification. | Ryan Sippy | worth considering | Week 9 technical specification |
| PR-06 | Clarity | The open questions are easy to spot, which should make the review discussion more focused. Raised in peer review. | Talk through late enrollment and notification behavior, then record the team's decisions. | Team | worth considering | Week 8 review |
| PR-07 | Clarity | SippyR could not get the requirements table to render in Markdown. | Fix the table separator so it declares all five columns, then check the rendered table. | Derek Corniello | worth considering | Week 8 submission |

## Summary of feedback

Clarity and scope came up most in the feedback: the traceability table did not render correctly at first, and the edge-case list felt long. The separator is fixed, and the table now focuses on 12 grouped scenarios. The grading error-path diagram and the links from requirements to design details also received positive comments.

## Two questions I raised in the review

1. If the runner accepts a job but never returns a result, what timeout and retry limits should the implementation use?
2. If a student joins or rejoins after an assignment is published, should they receive it, and how should that show up in analytics?

## Plan for the review slot

1. Spend about one third of the slot walking through the architecture, the grading failure path, and the traceability table.
2. Use the rest of the time for questions about edge cases, runner behavior, and late enrollment.
3. Write down any useful suggestion with its rubric criterion, action, owner, priority, and due date.
4. Keep the conversation relaxed. If a discussion changes a design decision, update the D2 rationale.
5. Put these notes at the end of the consolidated design PDF.
