# Qualtrics survey imports

These four Advanced TXT files contain the questions in Section 1.2 of the
[pilot protocol](../TECHNIVIEW_EXEMPT_DETERMINATION_REQUEST.pdf). Each file also
asks for the participant's full name and email address, as the protocol says
Qualtrics will record both with every survey response.

| When to use it | Import file |
| --- | --- |
| Before the four-week pilot | [Pre-pilot](pre-pilot.qualtrics.txt) |
| Before each optional session attended | [Pre-session](pre-session.qualtrics.txt) |
| After each optional session attended | [Post-session](post-session.qualtrics.txt) |
| After the four-week pilot | [Post-pilot](post-pilot.qualtrics.txt) |
| One-time instructor adoption survey (draft; requires IRB approval) | [Instructor adoption](instructor-adoption.qualtrics.txt) |

The instructor survey is a separate draft activity. It does not collect names,
email addresses, department, or course title. Before distribution, update the
IRB materials, verify Qualtrics metadata settings with UC, and obtain required
approval. Add only
IRB-approved screenshots using demonstration content after importing.

In UC Qualtrics, create a separate, empty Research Core survey for each file.
Open its **Survey** tab, then choose **Tools > Import/Export > Import survey**
and select the matching TXT file. Qualtrics adds a TXT import to the survey
you have open, so check that you are in the intended empty survey before
importing. [Qualtrics' import guide](https://www.qualtrics.com/support/survey-platform/survey-module/survey-tools/import-and-export-surveys/)
describes this process and the Advanced TXT format.

For the four student survey imports, preview every question. Confirm that the confidence,
preparedness, and ease-of-use choices appear in 1-to-5 order. Set **Full name**
and **Email address** to required and add email-format validation so each
response can be linked to a participant as described in the protocol. Set any
other response requirements in Qualtrics; the TXT files do not set them. Leave
the final open-response item in the post-session and post-pilot surveys
optional, as stated in the protocol.

For the instructor survey, make consent and eligibility responses required and
configure survey flow so a person who declines consent, is under 18, or is not
currently teaching a UC course exits before the survey questions. Configure
Qualtrics not to collect IP address, geolocation, contact-list, authenticator,
or other identifying metadata, as confirmed by UC's survey administrator.
Keep the response link generic and do not require login or personalized links.

Participants can attend more than one session. If you reuse a session survey
link each week, allow repeat submissions. Qualtrics' **Prevent Multiple
Submissions** setting can block someone who has already completed that survey
in the same browser. Individual Qualtrics links are single use, so send a new
one for each attended session. [Qualtrics' survey protection guide](https://www.qualtrics.com/support/survey-platform/survey-module/survey-options/survey-protection/)
explains those settings.

The questions about confidence and preparedness use the same wording and
response order in all four files. The TXT files are UTF-8 plain text and do not
contain participant responses. Treat the problem-count answers as categories,
not exact numeric counts, when analyzing exports.
