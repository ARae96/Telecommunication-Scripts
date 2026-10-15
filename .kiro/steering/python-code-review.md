---
inclusion: manual
name: Python Code Review
description: On-demand review of a Python file for code quality, correctness bugs, and documentation. Invoke with # in chat when you want a review, then reference the file to check.
---

# Python Code Review

Review the referenced Python file and report findings in three sections. Be
concise and focus on the most impactful issues; if a section has no issues, say
so briefly.

1. Code Review — code quality and style: unused imports/variables, error
   handling, PEP 8 issues, readability, duplicated logic, risky patterns (e.g.
   bare excepts, hardcoded values that belong in config/.env).

2. Bug / Correctness — likely runtime bugs and logic errors: unhandled
   API/network responses, missing exception handling, off-by-one or edge-case
   issues, incorrect data handling, resource leaks (unclosed files/connections).

3. Documentation — missing or outdated module/function docstrings, unclear
   naming, and a one-line summary of what the script does if documentation is
   thin.

Only analyze the file that was referenced. Do not modify the file unless the
user explicitly asks you to apply fixes.
