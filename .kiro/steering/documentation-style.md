---
inclusion: fileMatch
fileMatchPattern: '**/*.py'
---

# Code Documentation Style

Standards for how code documentation is written in this workspace. This covers
module docstrings, section banners, function docstrings, and inline comments.
The goal is documentation that a non-expert can read top-to-bottom and
understand at a glance.

The reference implementation for this style is
`src/Offline_Adherence_Datebricks.py`. When in doubt, match how that file is
documented.

## Reading Level (Required)

All documentation - module docstrings, function docstrings, and inline comments
- must read at roughly a **7th grade reading level**. Many readers of these
scripts are not full-time Python developers, so plain language matters more
than sounding technical.

"7th grade reading level" here does not mean simplistic or choppy. It means the
same plain, guiding voice used in the Workforce Management (WFM) knowledge base
(KB) articles. Those articles explain real processes to non-experts in full,
readable sentences. Write code documentation the same way. The rules below turn
that voice into concrete habits.

### Voice and person

- Explain to a reader, do not just label the code. Say what something does and
  why it matters, the way a KB walks a reader through a process.
- It is fine to use "we" for shared conventions and "you" for the person
  running or reading the script (e.g. "the IDs you enter by hand", "you can
  open in Excel"). This matches the KB voice and reads naturally.
- Lead with the rule or the point, then the reason, then the exception. This is
  the KB pattern: state what happens, explain why, then note the edge case.

### Sentence construction

- Write full, complete sentences with normal grammar and punctuation. Favor
  clear prose over terse fragments or note-style shorthand.
- One main idea per sentence. Aim for about 15-25 words. If a sentence runs
  long or chains several clauses with "and"/"but"/"so", split it into two.
- It is fine for a comment to be two or three sentences when the reader needs
  the "why" or a gotcha. The KBs use short paragraphs, not one-liners, when
  something needs explaining.
- Prefer the active voice ("the script writes a CSV") over the passive ("a CSV
  is written").

### Word choice and grammar

- Prefer common, everyday words over jargon. When a technical term is required
  (an SDK method name, "pre-signed URL", "management unit"), keep the rest of
  the sentence plain and, where helpful, say in a few words what it means.
- Match the KB habit of naming things exactly and consistently: use the real
  tool, file, and field names (Genesys, the .env file, a management unit ID)
  rather than vague references like "the thing" or "the config."
- Expand or briefly explain an acronym the first time it appears in a file
  (e.g. "management unit (MU)"), then the short form is fine.
- Be explicit about concrete values that matter - counts, thresholds, time
  windows, and grain (e.g. "one row per user per day", "waits up to 7 days").
  The KBs always give the specific number rather than a vague "a few."
- Use plain connective words ("so", "because", "when", "if") to show cause and
  condition, the same way the KBs explain why a step happens.

### Callouts for gotchas

- When something is easy to get wrong, flag it plainly the way a KB uses a
  "Please note" callout: say what the wrong path looks like and what to do
  instead (the reference file does this with its "URL that points nowhere"
  note).

A quick gut check: if a smart teammate who does not write Python - the kind of
person who reads the WFM KB articles - could not follow the comment on the
first read, simplify it. The comment should sound like it belongs in one of
those articles.

## Module Docstring / Header

Every script starts with a header block that explains the whole file before any
code. Follow the banner style used in `Offline_Adherence_Datebricks.py`:

- Open with a full-width banner line of `=` characters, the title, another
  banner line, then the description, and close with a final banner line.
- State in the first sentence or two what the script does, in plain language.
- Call out what is local-only vs. Databricks-only when the script runs in both
  places.
- Describe the output (files written, tables touched) and the grain of that
  output.
- Point to any sibling/related script by name.

Example shape (plain-language description, full-width `=` banners):

```python
# =============================================================================
# Genesys Cloud - Historical Adherence Pull (OFFLINE / LOCAL)
# =============================================================================
# Local-only version of the adherence pull. It signs in to Genesys Cloud, runs
# jobs for a list of management unit IDs you enter by hand, downloads the
# results, and writes CSV files you can open in Excel.
#
# Output (one timestamped CSV written next to this script):
#   adherence_final_local_<ts>.csv
#      One row per user for the pulled window.
# =============================================================================
```

## Section Banners

Separate the parts of a script with labeled section banners, matching the
existing style. Use a `#` line padded with dashes out to column ~79:

```python
# --- Imports -----------------------------------------------------------------
# --- Environment config ------------------------------------------------------
# --- Authentication ----------------------------------------------------------
# --- Helpers -----------------------------------------------------------------
# --- Main --------------------------------------------------------------------
```

Keep the labels short and in plain words that say what lives in that section.

## Function Docstrings

Every function gets a concise docstring. Follow the pattern in the reference
file:

- Start with a one-line summary that says what the function returns or does.
  Write it in plain language.
- If the function has side effects (writes a file, calls an API that changes
  state, prints output), say so.
- Describe the shape of what it returns when that is not obvious (e.g. "Returns
  a list of (payload, load date) tuples").
- Add a short extra paragraph only when the reader needs the "why" or a gotcha.
  Keep it plain and short.
- For a linear pipeline, number the steps in the docstring ("Step 1:",
  "Step 2:", ...) so the flow is easy to follow.

Example:

```python
def wait_for_adherence_job(job_id):
    """Wait for an adherence job to finish and return the finished job.

    Checks the job over and over until it reaches a final state. Raises a
    RuntimeError if the job fails or returns a state we do not expect, so a
    bad job is never treated as good data.
    """
```

## Inline Comments

- Comment for intent and gotchas, not to restate the code. Explain the "why".
- Put a short comment above non-obvious config or logic.
- When something is easy to get wrong, say what the wrong path looks like in
  plain words (the reference file does this well, e.g. the "URL that points
  nowhere" note).
- Keep comments to the same plain, KB-style reading level as the rest of the
  file (see Reading Level above): full sentences, everyday words, rule then
  reason.

## Acronym Glossary

Use this list as the single source of truth for what each acronym means. When
you spell out an acronym the first time it appears in a file, use the exact
definition shown here so every script says the same thing.

| Acronym | Definition |
|---------|------------|
| AML | Access Most Like |
| BU | Business Unit |
| KB | Knowledge Base |
| MU | Management Unit |
| WFM | Workforce Management |

### Prompt for unknown acronyms (Required)

When an acronym comes up that is not already in the glossary above, do not
guess what it means. Stop and ask the person you are working with for the
definition. After they give it, add the acronym and its definition to the
glossary table above so the next script can reuse it. This keeps every script
consistent and stops a wrong guess (like reading AML as "Assign Matching
License" instead of "Access Most Like") from spreading.

## Quick Checklist

Before saving a Python file, the documentation should:

1. Read at about a 7th grade level (short sentences, plain words).
2. Have a header banner that says what the script does and what it outputs.
3. Use labeled section banners to separate parts of the file.
4. Give every function a concise, plain-language docstring.
5. Use inline comments for intent and gotchas, not to restate code.
6. Expand acronyms the first time they appear, using the Acronym Glossary as
   the source of truth. If an acronym is not in the glossary, ask for its
   definition and add it before saving.
