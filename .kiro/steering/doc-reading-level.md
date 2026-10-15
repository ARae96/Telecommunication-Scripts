---
inclusion: manual
name: Documentation Reading Level
description: On-demand check that a Python file's documentation follows the workspace documentation style and reads at roughly a 7th grade reading level. Invoke with # in chat, then reference the file to check.
---

# Documentation Reading Level

Review ONLY the documentation in the referenced file (module header, section
banners, function docstrings, and inline comments) against the workspace Code
Documentation Style, whose reference implementation is
`src/Offline_Adherence_Datebricks.py`.

Focus on reading level and style, not code logic. Report findings concisely; if
a section is fine, say so briefly.

1. Reading Level — Flag any docstring or comment that reads above roughly a 7th
   grade reading level: long chained sentences, jargon where a plain word would
   do, unexplained acronyms on first use, or sentences much longer than ~15-20
   words. For each flagged item, quote the original and suggest a plainer
   rewrite.

2. Style Conformance — Check against the reference style: a header banner
   (full-width = lines) that says what the script does and what it outputs;
   labeled section banners (# --- Label ---); a concise plain-language docstring
   on every function; inline comments that explain intent/gotchas rather than
   restate code. Note anything missing or off-pattern.

3. Suggested Rewrites — For the most impactful issues, give ready-to-paste
   replacement text at the target reading level and style.

Only analyze the file that was referenced. Do not modify the file unless the
user explicitly asks you to apply the fixes.
