Generate an internal weekly insight email body from the weekly note.

Output format is STRICT JSON only (no markdown/code fences):
{
  "plain_body": "...",
  "html_body": "..."
}

Both `plain_body` and `html_body` must include this exact section structure:
- Greeting: Hello Team,
- Intro line mentioning this is weekly one-page pulse from Groww Play Store reviews.
- Mention PDF and CSV are attached for reference.
- Section: TOP 5 THEMES THIS WEEK
- Section: 3 ACTION IDEAS
- Section: TOP 5 REVIEW HIGHLIGHTS
- Section: DATA and APPLICATION
- Add application link line using provided link.

Line-break and layout rules (mandatory):
- After `Hello Team,` insert a blank line, then start the main matter on the next line.
- Keep each major section heading on its own line and highlight them.
- Insert a blank line between sections for readability.
- Keep bullet/numbered items each on separate lines.
- Do not collapse all content into one paragraph.

Closing format (mandatory):
Best regards,
Vadthyavath Shiva.

Auto-generated note (mandatory):
- Add this as the final line in italics.
- For `plain_body`, use markdown italics: *This is an auto-generated weekly insights email. No replies are expected.*
- For `html_body`, use HTML italics: <em>This is an auto-generated weekly insights email. No replies are expected.</em>

Quality and style:
- Professional, executive-ready tone.
- Bold section headings and important keywords in `html_body` using <strong>.
- Preserve facts from weekly note.
- Keep exactly 5 themes, exactly 3 action ideas, exactly 5 review highlights.
- No PII.

Hard constraints:
- Return only valid JSON.
- Do not wrap JSON in markdown fences.
- Do not prefix with words like "html" or "json".
- Do not include Subject/To fields.
