---
inclusion: manual
name: genesys-virtual-agent-builder
description: Schema, conventions, and patterns for authoring Genesys Cloud agentic virtual agent JSON. Use when building, editing, or reviewing a Genesys Cloud virtual agent / AVA definition.
---
# Genesys Cloud Agentic Virtual Agent Builder

Use this when creating or editing a Genesys Cloud agentic virtual agent definition. It describes the JSON schema, the authoring conventions, and a validation checklist, all derived from a known-good production example (the WGU "Sage" assistant).

## Reference example

A complete, working definition is kept alongside this file. Read it before authoring a new agent so the new one matches its structure and tone.

#[[file:examples/sage-wgu-virtual-agent.json]]

## Skeleton template

When starting a new agent, copy this skeleton and fill in the `<PLACEHOLDER>` tokens. It encodes the required conventions (precedence-first instruction, auth gate, empty-result handling, standard events) so a new definition is structurally correct from the start.

#[[file:examples/agent-skeleton.json]]

## Top-level shape

Everything lives under a single `definition` object:

```jsonc
{
  "definition": {
    "role": "string — the system persona and scope",
    "instructions": ["string", ...],      // ordered behavioral rules
    "guardrails": { "custom": [ { "instruction": "...", "enabled": true } ] },
    "tools": [ /* KnowledgeSetting and DataAction tools */ ],
    "types": [ /* input and output type definitions */ ],
    "events": [ /* UserExit, Escalation, Guardrails messages */ ],
    "settings": { "comfortStatement": { "enabled": true } },
    "model": "Stable"
  }
}
```

### `role` (required)

The persona and scope prompt. Conventions from the example:

- Open with identity: who the agent is, the channel, and who the user is ("You are Sage, ... available by chat. The person you are helping is the student.").
- State plainly that it is an AI, not a human, and to say so if asked.
- List what it CAN help with, then what it must route elsewhere.
- Define personality and a target reading level (the example uses "roughly 7th- to 8th-grade").
- State sourcing rules (approved knowledge only, no general world knowledge for policy/pricing).
- State auth and privacy boundaries (never display SSN/full account numbers).
- Close with hard limits (no admissions decisions, no legal/medical/financial advice, distress routing).

### `instructions` (required)

An ordered array of behavioral rules. Patterns:

- Put a **conflict-resolution precedence rule first** so the model knows which rule wins (safety → human/account requests → acknowledge-without-searching → clarify → knowledge search).
- One rule per concern; keep each rule self-contained and imperative.
- Encode conversation memory explicitly (remember the student's program of interest; update it if they change).
- Specify the exact greeting and the exact escalation phrasing when wording matters.
- Separate "when to clarify" from "when to search" from "when to escalate".

### `guardrails.custom` (required for safety)

Array of `{ "instruction": string, "enabled": boolean }`. These are hard "do not" rules enforced separately from `instructions`. Keep them short and absolute (no eligibility determinations, no policy exceptions, route distress to humans, never accept a user-supplied `opportunity_id`).

## `tools`

Two tool kinds appear:

### `KnowledgeSetting`

A knowledge-base search tool.

```jsonc
{
  "type": "KnowledgeSetting",
  "name": "wgu_edu",
  "description": "when/what this searches",
  "inputInstructions": ["when to call / when NOT to call / how to phrase the query", ...],
  "outputInstructions": [
    { "type": "Python", "when": "lambda result: len(result) == 0", "then": "what to say" },
    { "type": "Python", "when": "lambda result: len(result) > 0",  "then": "what to say" }
  ],
  "target": { "id": "<knowledge settings guid>", "name": "...", "selfUri": "/api/v2/knowledge/settings/<guid>" }
}
```

### `DataAction`

A backend integration call (e.g. Databricks via a Genesys custom Data Action).

```jsonc
{
  "type": "DataAction",
  "name": "get_opportunity",
  "description": "what it returns + when to call",
  "inputInstructions": [ "call ONLY if ...", "never ask the user for ...", ... ],
  "outputInstructions": [ /* routing rules keyed on the result, see below */ ],
  "target": { "id": "custom_-_<guid>", "name": "[STAGE] ...", "selfUri": "/api/v2/integrations/actions/custom_-_<guid>" },
  "inputs": [
    { "targetName": "opportunityID", "type": "OpportunityId", "source": "External",  "required": false, "fallbackToUser": false, "dependencyOnly": false },
    { "targetName": "programCode",   "type": "OpportunityResult", "source": "ToolOutput", "mapping": ["OpportunityResult", "programCode"], "required": false, "fallbackToUser": false, "dependencyOnly": false }
  ],
  "output": "OpportunityResult",
  "schemas": { "inputs": { /* JSON Schema */ }, "outputs": { /* JSON Schema */ } }
}
```

Tool conventions:

- `name` is a stable snake_case identifier referenced in instructions.
- `inputInstructions` gate *when* the tool fires. Encode preconditions ("call only after `get_opportunity`"), auth gates ("only if `opportunity_id` is in the start context"), and the "never ask the user for X" rule.
- `inputs[].source`:
  - `External` — value comes from the start context (e.g. `opportunity_id`). Pair with `fallbackToUser: false` for anything that must never be user-supplied.
  - `ToolOutput` — value comes from a prior tool's output; add `mapping: ["<OutputType>", "<field>"]`.
- `output` names the result type (must match a `types` entry).
- `schemas` holds JSON Schema for inputs and outputs; keep field names identical to the live Data Action (preserve typos like `scondaryTuitionSource` — comment the typo in the matching `types` entry).

### `outputInstructions` (result-driven routing)

A list of condition → response rules evaluated against the tool result. Two styles:

- **Python**: `{ "type": "Python", "when": "<python expr over `result`>", "then": "instruction" }`. Use for list emptiness, string checks, compound conditions.
- **Structured**: `{ "type": "Structured", "when": { "group": "And"|"Or", "rules": [ { "mapping": ["<Type>","<field>"], "operator": "IsNull"|"IsNotNull"|"Equal", "value": "..." } ] }, "then": "instruction" }`. Use for simple field comparisons.

Patterns:

- Always cover the empty/null result case with a graceful fallback (apologize + offer a human).
- For parallel-array outputs, state explicitly that arrays are zipped by index (row `i` across all arrays is one record).
- Put sensitive-handling rules in `then` (never read internal status codes verbatim; never state dollar amounts).

## `types`

Reusable type definitions referenced by tools.

- Scalar alias: `{ "name": "OpportunityId", "type": "string", "userUtteranceSubstring": false }`.
- Agent input: `{ "name": "InputData", "direction": "AgentInput", "type": "object", "properties": [ { "name": "opportunity_id", "type": "OpportunityId", "required": false } ] }` — this is how start-context values enter the agent.
- Tool output: `{ "name": "OpportunityResult", "direction": "Output", "type": "object", "properties": [ ... ] }` — one entry per `DataAction.output`.
- Field entries: `{ "name", "type", "required", "description", "items" }`. For arrays, `type: "array"` plus `items: "string"`.
- Use `description` to carry handling rules the model must honor (e.g. "Never read `careStatus` verbatim"). This is the right place for data-sensitivity notes.

## `events`

Fixed system messages:

```jsonc
{ "type": "UserExit",   "message": "..." }
{ "type": "Escalation", "message": "..." }
{ "type": "Guardrails", "message": "...", "violationThreshold": 3, "violationThresholdCrossedMessage": "..." }
```

## `settings` and `model`

- `settings.comfortStatement.enabled` — whether the agent emits a "give me a moment" style filler during tool latency.
- `model` — the model tier (the example uses `"Stable"`).

## Authoring conventions (carry these into every new agent)

1. **Precedence first.** The first `instructions` entry resolves conflicts between all later rules.
2. **General vs. personal split.** Decide early whether a question is general (knowledge base) or personal/account-specific (Data Action + auth gate). Never answer personal questions from general FAQs.
3. **Auth gate on all account data.** Account Data Actions fire only when the authenticated identifier (e.g. `opportunity_id`) arrives in the start context. The user may never supply it — enforce in `inputInstructions`, `guardrails`, and `inputs[].fallbackToUser: false`.
4. **Tool ordering.** A profile/context Data Action (here `get_opportunity`) runs first; later tools depend on its output via `source: "ToolOutput"`.
5. **Every tool handles the empty result.** Each tool's `outputInstructions` must gracefully handle no-data (apologize + offer a human) and avoid inventing data.
6. **Clarify, don't guess.** When one targeted search can't be formed, ask exactly one clarifying question; don't dump a multi-topic overview.
7. **Retry knowledge once.** Rephrase and search a second time before telling the user nothing was found.
8. **Data-sensitivity in descriptions.** Put "never read verbatim / never state amounts" rules on the relevant `types` field descriptions and in the tool `then` text.
9. **Preserve live field names.** Mirror the real Data Action schema exactly, typos and all; note the typo in the type description.
10. **GUIDs and `selfUri`.** `target.id`/`selfUri` must point at real Genesys resources (knowledge settings or custom integration actions). Keep `[STAGE]`/`[PROD]` prefixes consistent with the environment.

## Validation checklist (run before shipping a definition)

- [ ] `definition.role` sets identity, scope, personality, reading level, sourcing, auth/privacy, and hard limits.
- [ ] First `instructions` entry is a precedence/conflict rule.
- [ ] Greeting and escalation wording are specified where exact phrasing matters.
- [ ] Each `tools[].name` referenced in instructions exists, and vice versa.
- [ ] Every `DataAction.output` has a matching `types` entry; every `inputs[].type` resolves to a `types` entry.
- [ ] `ToolOutput` inputs include a `mapping` to an existing output type/field.
- [ ] Each tool's `outputInstructions` cover both the empty/null and populated cases.
- [ ] Parallel-array outputs state the zip-by-index rule.
- [ ] Auth gate present on every account Data Action (`External` source, `fallbackToUser: false`, "never ask the user" instruction, matching guardrail).
- [ ] `guardrails.custom` cover eligibility/approval limits, policy exceptions, distress routing, and identifier handling.
- [ ] `events` include UserExit, Escalation, and Guardrails (with threshold + crossed message).
- [ ] JSON is valid and the `target` GUIDs/`selfUri`s point to real resources in the right environment.

## Build and publish (ava-harness lifecycle)

Authoring the JSON is only half the job — this section covers turning a definition into a live AVA via the `ava-harness` MCP tools. These rules are distilled from the `ava-build` skill plus hard-won validation lessons; the vendor skill (`.kiro/skills/ava-build/SKILL.md`) is overwritten on `ava-mcp update`, so the durable version of this knowledge lives here.

### Lifecycle position

```text
dispatch → design ⇄ knowledge → build → test → evaluate → critique
```

Build sits after design: it reads the design artifact (or an in-memory definition), validates, calls `create_version`, then `publish_version`. The MCP tools do all payload transformation — never hand-assemble the wire JSON.

### The core build tools

- `create_ava` — new AVA shell (idempotent; returns the existing one if the name matches). Skip in update mode; reuse the existing `agentId`.
- `create_version` — Pydantic-validates the whole definition locally before any HTTP call. A bad payload fails here with a precise field error, *before* it reaches Genesys. Fix the field and retry; do not guess.
- `publish_version` — runs a publish job and blocks until it settles. `testOnly: true` → TestReady (safe for Cicero testing/eval, no production traffic). `testOnly: false` → ProductionReady (locks the version contract and routes live Botflow traffic).
- `get_latest_saved_version` — most recent version of any status (edit from here). `get_latest_published_version` — latest ProductionReady only.

### Update flow (the safe edit loop)

To change a live AVA: `get_latest_saved_version` → modify the returned `definition` → `create_version` (new version number) → `publish_version`. Always edit from the fetched current state, not from memory, so you don't silently drop a field. Each `create_version` increments the version; validation-failed calls do not consume a number.

### Pre-flight validation (catch these before `create_version`)

The MCP layer enforces these, but knowing them up front avoids 422 round-trips. Every one below was a real failure in practice:

1. **`fallbackToUser` is only valid on `External`-sourced inputs.** On a `User`- or `ToolOutput`-sourced input it is rejected. (Error: "Fallbacks can only be specified for external sources.")
2. **A `User`-sourced tool input must reference a type with `direction: "input"`.** A bare primitive, or a type without input direction, is rejected. Create a named input-direction alias (e.g. `Username`, `StudentEmail`).
3. **A `ToolOutput`-sourced input's `type` must be the producer's output *type name*, not the primitive of the mapped field**, and that type must be declared `direction: "output"`. Add `mapping: ["<OutputType>", "<field>"]`.
4. **Every `DataAction.output` type must exist in `types[]` with `direction: "output"`.**
5. **`role` has a hard 5000-character limit.** Keep the role lean: identity, scope, voice, gates, privacy, hard limits. Put detailed enumerations (full verification field lists, per-branch tool logic) in `instructions[]` and tool config, not duplicated in the role. When adding to the role, draft it and count characters before submitting.
6. **Enum string values must be valid identifiers** (`^[A-Za-z_][A-Za-z0-9_]*$`) — PascalCase like `ExpiringSoon`, never `Expiring Soon`.
7. **Start Context (`InputData`, `direction: "agentInput"`) rules:** no `description` on the `InputData` object itself (reserved); no `required: true` properties (always rejected — gate via a tool input with `fallbackToUser` instead); each property aliases a bare primitive (no inline primitives, no enums); property names are snake_case with at least one underscore (e.g. `opportunity_id`).
8. **External required inputs must set `fallbackToUser: true`** and reference a type that is declared as a Start Context property.

### Guardrails vs. instructions (a convention the critique enforces)

Guardrails should block *input categories* or enforce *action preconditions / data privacy* — hard "do not" rules. Behavioral coaching ("when the user does X, respond with Y") belongs in `instructions[]`, not guardrails. If a guardrail reads like a response directive rather than a block, move it to instructions. (This exact fix came up in critique: a "respond to human-help requests with more than a clarifying question" rule was moved from guardrails into instructions.)

### Publish-time (`publish_version`) failure handling

- **`Succeeded`** → proceed.
- **`Failed` with a 4xx / `bad.request`** → deterministic payload problem. Retrying the same payload fails identically. Read `errors[].details[].fieldName`, fix that field, re-run `create_version`, publish again. A common cause: an `outputInstructions[].when` that the publish backend rejects.
- **`Timeout` or 5xx** → transient; safe to retry the same payload (or raise `AVA_PUBLISH_POLL_TIMEOUT`).
- **`403 missing.permissions: agentic:virtualAgentVersionJob:add`** → the OAuth client lacks the publish-job grant. This is an org-side role fix, not a payload issue; publishing must be done by someone whose client has the grant (or manually in the UI). Do not retry blindly.

### Production-publish gate

Only promote to production (`testOnly: false`) after: the eval scorecard passes threshold, the critique has no blocking errors, and the author has explicitly asked to promote. Production publish locks the version contract and routes live traffic — confirm with the author first.

### Mock Data Actions (for test/eval before real backends exist)

- `create_mock_data_action` builds a function-backed (or echo) Data Action returning deterministic fake data; it validates end-to-end on create. Requires `integrations:actionFunction:*` grants (function path) in addition to `integrations:action:*`.
- `replace_mock_responses` replaces the whole mock *response table* only — it does NOT change the input/output *schema*. To change the declared shape (e.g. add an output field, change an input name), recreate the action with `create_mock_data_action`.
- Mocks match cases by exact input; an unmatched input returns the `defaultMock`. To test a branch keyed on an output field (e.g. an `idm_account_claim: true` path), add a case whose input is a value the verified profile actually produces, or add a second profile to the upstream mock so that value flows through.
- Returning secrets (temp passwords, PINs) inline in chat is acceptable for a mock but not production-appropriate — flag it and plan out-of-band delivery for the real backend.

## Build-and-publish checklist

- [ ] Editing a live AVA: fetched current state with `get_latest_saved_version` before modifying.
- [ ] `role` is under 5000 characters (drafted and counted if near the limit).
- [ ] Every `User`-sourced input references an `input`-direction type; every `ToolOutput` input references an `output`-direction type with a `mapping`.
- [ ] `fallbackToUser` appears only on `External`-sourced inputs.
- [ ] Start Context `InputData` has no `description`, no `required` properties, snake_case property names aliasing primitives.
- [ ] Guardrails are blocks/preconditions; behavioral directives live in instructions.
- [ ] Published as TestReady first; production promotion only after eval + critique pass and explicit author approval.
- [ ] Any mock Data Action validated on create; schema changes done via recreate, not `replace_mock_responses`.
