# Techniview User Stories
## Team Members: Ryan Sippy, Jason Bellerjeau, Derek Corniello

## Stakeholders:
### Primary Stakeholders:
+ Students
+ Professors

### Secondary Stakeholders:
+ Problem Management Team
+ IT Support Team

### Hidden Stakeholders:
+ Students with Disabilities
+ Government Education Departments and Regulators
+ University Administrators

## User Stories:
### US-01(Primary):
As a student, I want to be able to access and run practice coding problems in a web-based environment, so that I can improve my coding skills without needing to set up a local development environment.

### US-02(Primary):
As a student, I want to track my progress and performance on coding problems, so that I can identify areas where I need to improve and monitor my growth over time.

### US-03(Primary):
As a professor, I want to be able to assign and manage coding problems for my students, so that I can provide them with relevant practice material and assess their understanding of the course content.

### US-04(Secondary):
As a member of the problem management team, I want to be able to easily create and curate coding problems, so that I can ensure the quality and relevance of the problems available on the platform.

### US-05(Hidden):
As a University Administrator, I want to ensure that the platform complies with data privacy and security regulations, so that students' personal information and coding submissions are protected.

## Use Cases:
### UC-01(Expands on US-01):
Title: Accessing and Running Practice Coding Problems

Primary Actor: Student

Precondition: Student has an account on the platform and is logged in.

Main Flow:
1. Student navigates to the coding problems section of the platform and selects a problem to work on.
2. The platform displays the problem statement, input/output specifications, and any relevant constraints.
3. Student writes their solution in the provided code editor and submits it for evaluation.
4. The platform compiles and runs the student's code against a set of test cases.
5. The platform provides feedback on the student's submission, including whether it passed or failed the test cases and any relevant error messages.

Alternative Flow:
Student chooses to view hints or solutions for the problem, which may provide guidance on how to approach the problem or reveal the correct solution.

Exception Flow:
If the student's code fails to compile or run, the platform will display an error message and allow the student to correct their code and resubmit it.

Postcondition: Student receives feedback on their submission and can choose to attempt the problem again or move on to a different problem.

### AC-01.1:
Given a student is logged in and has selected a coding problem, when they submit their code, then the platform should compile and run the code against the provided test cases and return feedback on the submission.
