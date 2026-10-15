---
inclusion: manual
name: KB Authoring Style
description: How to write Workforce Management (WFM) knowledge base (KB) articles as HTML. Covers voice, structure, the accordion layout, reusable components, and the WGU house style. Use when creating or editing KB HTML articles.
---

# KB Authoring Style

How to write Workforce Management (WFM) knowledge base articles for Western
Governors University (WGU). These articles are published as HTML in ServiceNow
and read by two kinds of people: individual contributors (ICs) who follow the
process, and WFM analysts who run it. Match this style so new articles look and
sound like the ones already published.

The reference articles for this style live in the KB library. When in doubt,
match how these are written:

- External (for ICs and leaders): `IC Communication KB V13`,
  `Catalog Walk Through V5`, `Leader Communication KB V7`.
- Internal (for WFM analysts): `Schedule Updating V2`,
  `Activity Code and Descriptions V2`, `Schedule Auditing V3`.

Always work from the **newest version number** of an article (e.g. V13 over
V12) as the source of truth for current style.

## Voice and Tone

Write in a warm, plain, second-person voice. The reader should feel guided, not
lectured.

- Address the reader as "you"; refer to the team as "we" and "Workforce" (or
  "WFM"). This shared voice is the heart of the house style.
- Be direct about what the reader must do, may do, and must not do. State the
  rule, then the reason.
- Keep it professional but human. It is fine to acknowledge hard moments (the
  bereavement section in `IC Communication` opens with "The loss of a family
  member is never easy"). Lead with empathy on sensitive topics, then give the
  steps.
- Spell out the "why" behind a rule so the reader understands the intent, not
  just the instruction.
- Prefer full sentences and short paragraphs over terse fragments. These
  articles explain; they do not just list.
- Use everyday words. When a WFM term is needed (activity code, management
  unit, adherence), use it plainly and, on first use, say in a few words what
  it means.
- Expand an acronym the first time it appears, then use the short form:
  "individual contributor (IC)", "AutoHotkey (AHK)".

## Naming and Terminology (WGU House Style)

- The team is **Workforce Management**, shortened to **WFM** or **Workforce**.
- Individual contributors are **ICs**; their managers are **leaders** (not
  "managers" or "supervisors").
- Tools and systems are named exactly: **Genesys**, the **Time Off Tool**, the
  **Tempo App**, **ServiceNow**, **Workday**, **People Center**, **Owledge**,
  **AutoHotkey (AHK)**.
- Reference other KBs by their article number as a link, e.g. `KB0022500`. When
  an article is not published yet, use the placeholder `KBXXXXXX`.
- Times are Mountain Time — "MST or MDT, whichever is currently in use." Use
  that phrasing rather than a bare "MST."

## Document Structure

Every article is a standalone HTML file. Follow this skeleton:

```html
<!DOCTYPE html>
<html lang="en" xmlns:mso="urn:schemas-microsoft-com:office:office" xmlns:msdt="uuid:C2F41010-65B3-11d1-A29F-00AA00C14882">
<head>
    <title>Article Title</title>
    <link rel="stylesheet" href="../_Styles/Style.css">

<!--[if gte mso 9]><xml>
<mso:CustomDocumentProperties>
<mso:_ApprovalStatus msdt:dt="string">0</mso:_ApprovalStatus>
<mso:_ApprovalAssignedTo msdt:dt="string"></mso:_ApprovalAssignedTo>
<mso:_ApprovalRespondedBy msdt:dt="string"></mso:_ApprovalRespondedBy>
</mso:CustomDocumentProperties>
</xml><![endif]-->
</head>
<body>
    ...
</body>
</html>
```

- Keep the `mso` namespace on `<html>` and the `CustomDocumentProperties`
  comment block in `<head>`. This is the SharePoint/ServiceNow approval
  metadata; leave it in place with `_ApprovalStatus` of `0`.
- Link the shared stylesheet with `<link rel="stylesheet" href="../_Styles/Style.css">`.
  Do not restyle inline; the shared CSS defines the whole look.
- Give the file a clear `<title>`. Optionally add a one-line short description
  as an HTML comment right after `</head>`, e.g.
  `<!--Short Description: Individual Contributor Communication Expectations for Workforce Management-->`.

### Headings

- Use a single `<h1>` for the article title when the article names itself
  (internal how-to articles do this, e.g. "Process for Manually Updating
  Schedules"). Some external articles skip `<h1>` and open at `<h2>`; match the
  sibling article you are editing.
- Open the body with an `<h2>General Information</h2>` section that sets context
  before any accordions. This overview is expected in nearly every article.
- Use `<h2>` and `<h3>` for further sectioning outside accordions. Bigger
  heading number means smaller text.

## Accordions (Primary Layout)

Collapsible accordions are the main way articles are organized. Each top-level
topic is a `level1` accordion; sub-topics nest as `level2` (and `level3` when
needed). The CSS colors them: `level1` is navy (`#003057`), `level2` is blue
(`#327da9`), `level3` is grey (`#63666a`).

Single-level accordion:

```html
<div>
    <section class="accordions">
    <details class="level1">
        <summary tabindex="0">Topic Title</summary>
            <p>Explanation of the topic.</p>
    </details>
    </section>
</div>
```

Nested accordions (a topic with sub-topics):

```html
<div>
    <section class="accordions">
    <details class="level1">
    <summary tabindex="0">Topic Title</summary>
        <p>Optional intro paragraph for the whole topic.</p>
        <section class="accordions">
        <details class="level2">
        <summary tabindex="0">Sub-topic Title</summary>
            <p>Details for the sub-topic.</p>
        </details>
        </section>
    </details>
    </section>
</div>
```

Rules for accordions:

- Always keep `tabindex="0"` on every `<summary>` for keyboard access.
- Wrap each top-level accordion in its own `<div>` and `<section class="accordions">`.
- Nest a `level2` inside its parent by placing a new
  `<section class="accordions"><details class="level2">` before closing the
  parent `</details>`.
- Add `open` after the class to force an accordion expanded on load, e.g.
  `<details class="level1" open>`. Use this sparingly.
- Give each `level1` topic a short intro paragraph before its sub-accordions
  when it helps orient the reader (see `Schedule Updating`).
- An `FAQ` accordion at the end is a common and welcome pattern: a `level1`
  "FAQ" holding one `level2` per question, with the question as the summary.

## Reusable Components

Use these building blocks from the shared stylesheet instead of inventing new
markup.

### Please-note / callout asides

For a callout or reminder, use a `please-note` aside with a bolded lead-in:

```html
<aside class="please-note">
    <p><strong>Please note: </strong>Your reminder text here.</p>
</aside>
```

- Add `class="please-note critical"` for a more serious warning (the `critical`
  modifier switches the accent bar to red, `#840028`).
- Add `indent-once` or `indent-twice` to indent the aside when it sits under
  nested content.

### Links

Always open links in a new tab and mark them safe:

```html
<a href="https://example.com" target="_blank" rel="noopener noreferrer">Link text</a>
```

- Use descriptive link text (the tool name or KB number), not "click here."
- For email links use `<a href="mailto:WFM@wgu.edu">WFM@wgu.edu</a>`.

### Lists

- Use `<ol>` for ordered steps or numbered form fields, `<ul>` for unordered
  sets of options or rules.
- Keep each `<li>` to a single, complete thought.

### Tables

Reference-style articles (like activity codes) use tables to pair a term with
its explanation:

```html
<table>
    <tbody>
        <tr>
            <th scope="col" style="width: 125px; white-space: nowrap;">Activity Code</th>
            <th scope="col">Explanation</th>
        </tr>
        <tr>
            <td style="background-color: #b6e8fc; white-space: nowrap;">Shadowing</td>
            <td>When and how this code is used, in full sentences.</td>
        </tr>
    </tbody>
</table>
```

- Keep `scope="col"` on header cells for accessibility.
- Use a fixed width and `white-space: nowrap;` on the first column so the term
  stays on one line.
- Cell background colors are used to group related codes; reuse the same color
  for codes in the same family (e.g. break/meal codes share a shade).

### Leader/Agent audience tags

When a form or process is meant for a specific audience, call it out in red at
the top of the section, matching `Catalog Walk Through`:

```html
<p><strong><span style="color: #c6033d;">Leader Only Form</span></strong></p>
```

Use "Leader Only Form", "Agent Form", or "Leader and Agent Form" as fits.

## Writing the Content

- Open with `General Information` that explains the whole article in a few
  plain paragraphs before diving into accordions.
- Lead each process with the rule, then the reason, then the exception. Example
  pattern from `Schedule Updating`: state the request type, when WFM will act,
  and what confirmation is required first.
- Be explicit about thresholds and timeboxes that matter (e.g. "5 or more
  minutes," "acknowledged within 10 minutes," "30 minutes of notice"). These
  concrete numbers are part of the house style.
- Name the exact channel or tool for each action (Time Off Tool, a specific
  Teams channel, `WFM@wgu.edu`, a ServiceNow catalog item) rather than a vague
  "reach out."
- On confidential topics (leaves of absence, accommodations), state plainly
  that WFM does not need and does not want the private details, and keep the
  guidance high level.
- Close the article with an FAQ accordion when there are common follow-up
  questions.

## Quick Checklist

Before saving a KB HTML file, confirm it:

1. Uses the standard HTML skeleton, keeps the `mso` approval metadata, and links
   `../_Styles/Style.css`.
2. Opens with a `General Information` overview before any accordions.
3. Organizes topics as `level1` / `level2` accordions, each `<summary>` with
   `tabindex="0"`.
4. Speaks in the "you / we / Workforce" voice, warm and plain, rule then reason.
5. Uses WGU terms exactly (ICs, leaders, Genesys, Time Off Tool, MST/MDT).
6. Expands acronyms on first use and links other KBs by number.
7. Uses `please-note` asides, `target="_blank" rel="noopener noreferrer"` links,
   and colored tables from the shared styles rather than new markup.
8. States concrete thresholds, channels, and tools instead of vague guidance.
9. Ends with an FAQ accordion when there are common questions.
