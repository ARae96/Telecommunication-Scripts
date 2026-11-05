# Python Scripting Standards (Coding Workspace)

These standards are derived from the existing scripts in `src/` (Genesys Cloud
automation and Databricks adherence pulls). Follow them when writing or editing
Python in this workspace so new scripts match the established conventions.

## Domain & Stack

- All scripts automate **Genesys Cloud** via the official SDK
  `PureCloudPlatformClientV2` (pinned in `requirements.txt`).
- Runtime dependencies live in `requirements.txt` with **pinned versions**
  (e.g. `python-dotenv==1.0.1`). Pin any new dependency you add. The SDK
  version is whatever `requirements.txt` says, so check there instead of
  copying the number into other files.
- Local runs assume `pip install -r requirements.txt` plus a populated `.env`.
- Some scripts double as **Databricks notebooks** and use `spark`, `display`,
  `dbutils`, and `%sql`, which only exist in the Databricks runtime.

## Credentials & Authentication

- Never hard-code credentials. Read them from the environment.
- Local credentials come from a **git-ignored `.env`** at the workspace root.
  New variables must also be documented in `.env.example` with placeholder
  values (real values never committed).
- Current credential variables: `GENESYS_CLOUD_CLIENT_ID`,
  `GENESYS_CLOUD_CLIENT_SECRET`, `GENESYS_CLOUD_REGION`.
- **Do not write your own `build_apis()`.** Import it from the shared module
  `src/genesys_common.py` (see "Shared Module" below) and name the clients the
  script needs:
  ```python
  from genesys_common import build_apis
  wfm_api, users_api = build_apis('WorkforceManagementApi', 'UsersApi')
  ```
  Clients come back in the order requested. Asking for one client returns it on
  its own (not in a tuple). The shared `sign_in()` does the work every script
  used to repeat:
  1. Loads `.env` from the workspace root (one folder above `src/`).
  2. Reads client id/secret via `os.environ.get(...)`.
  3. Raises `SystemExit` with a helpful message if either is missing
     (point the user at copying `.env.example` to `.env`).
  4. Authenticates with client credentials
     (`ApiClient().get_client_credentials_token(client_id, client_secret)`).
- In Databricks, a local module is not importable from a notebook unless it is
  packaged for the cluster. Notebook scripts keep their own sign in and read
  the secrets from a scope, e.g.
  `dbutils.secrets.get(scope="purecloud", key="clientId")`. Keep this the only
  spot that changes between local and Databricks auth. `sign_in()` also accepts
  a client id and secret as arguments if the module is available there.

## Script Structure

- Order every script: module docstring → imports → configuration constants →
  setup → helpers → step functions → `main()`. Setup is usually just the
  `build_apis(...)` call inside `main()`, because sign in lives in
  `genesys_common.py`.
- Use labeled section banners to separate concerns, matching the existing style:
  ```python
  # --- Configuration ---------------------------------------------------------
  # --- Setup -----------------------------------------------------------------
  # --- Helpers ---------------------------------------------------------------
  # --- Steps -----------------------------------------------------------------
  # --- Main ------------------------------------------------------------------
  ```
- Wrap execution in `def main():` and guard it with
  `if __name__ == '__main__': main()`.
- Break work into small, single-purpose functions with descriptive names
  (`get_role_user_ids`, `find_users_to_migrate`, `remove_old_role`). Keep each
  function simple and easy to read (see Simplicity & Readability below). Number
  the pipeline steps in docstrings ("Step 1:", "Step 2:", ...) when a script
  runs a linear flow.
- Give every function a concise docstring describing what it returns and any
  side effects.

## Shared Module: `src/genesys_common.py`

Common Genesys reads live in one shared module so scripts import them instead
of rewriting them. It sits next to the scripts, so a plain import works (the
same way `confirm_prompt.py` is imported):

```python
from genesys_common import build_apis, get_role_user_ids, get_role_name
```

**Check the module before writing a helper.** If a script needs one of the
things below, import it. Do not copy it into the script.

| Area | Functions |
|------|-----------|
| Sign in | `sign_in`, `build_apis` |
| Safe calls | `call_api` (retries on a 429), `split_into_batches` |
| Single name lookups | `get_user_name`, `get_role_name`, `get_queue_name`, `get_group_name`, `get_division_name`, `get_flow_name` (each returns `NAME_UNAVAILABLE` on failure) |
| Many-ID name lookups | `get_user_names`, `get_queue_names` (return an ID to name dict; take `known_names` and `missing_name`) |
| Lists of people | `get_all_users`, `get_role_user_ids`, `get_queue_user_ids` |
| Roles | `get_role_with_permissions`, `get_user_role_ids`, `get_user_grant_division_ids`, `policy_key`, `get_role_permission_strings` |
| BUs and MUs | `get_business_unit_id_from_link`, `get_business_units`, `get_business_unit_names`, `get_bu_name_and_start_day`, `get_management_units`, `get_management_unit_names` |
| Week dates | `get_past_week_dates`, `format_week_folder_name` |
| Files and data | `to_plain_data`, `convert_keys_to_snake_case`, `fetch_json_from_url`, `clean_folder_name`, `write_json_file`, `write_csv_file` |

Rules for using and growing the module:

- **Read-only only.** The module never changes anything in Genesys. Code that
  grants, removes, deletes, or updates stays in the script, next to its
  confirm step.
- **Add to the module when a second script needs it.** When you write a helper
  that a second script would also use (same API call, used the same way), move
  it into `genesys_common.py` and import it in both. Keep one-off logic in the
  script. This follows "avoid premature abstraction": wait for a real, repeated
  need.
- **Keep the module's style.** Plain names, a docstring on every function,
  `try/except ApiException`, a fallback value instead of a crash for name
  lookups, and no clever tricks. Scripts that need a different fallback text
  pass it in (for example `missing_name='Deleted Queue'`) instead of editing
  the shared default.
- **Do not change a shared function's behavior casually.** Many scripts import
  it. If a script needs different behavior, add a parameter with a default
  that keeps today's behavior.
- **Pagination, batching, and name lookups come from the module.** Do not
  reimplement them. If a script keeps its own page size or batch size constant,
  it should be because the script uses it somewhere the module does not.
- **Update the module's header list and the table above** when you add or
  rename a function.
- **Notebook exception:** Databricks notebook scripts (for example
  `Online_Adherence_Datebricks.py`) do not import the module. See Credentials
  above.

## Configuration Conventions

- Put all tunables in a configuration block near the top of the file as
  module-level constants in `UPPER_SNAKE_CASE`
  (`PAGE_SIZE`, `DIVISION_SUFFIX`, `INCREMENTAL_LOOKBACK_DAYS`,
  `ADHERENCE_TIME_ZONE`, `TABLE_*`).
- Keep lakehouse/table names as constants used as the single source of truth
  (e.g. `TABLE_BUSINESS_UNITS = "wgu_lakehouse.genesys.stg_business_units"`).
- Explain non-obvious config with an inline comment right above it.

## Safety: Confirm Dialog for Mutations

Do **not** add a `DRY_RUN` flag. Any script that **modifies** Genesys state
(grant/remove roles, add group members, delete, bulk update, publish a flow)
uses a read, preview, confirm, apply flow instead. Every run previews first, so
there is no toggle to forget to flip.

The confirm helper lives in `src/confirm_prompt.py`:

```python
from confirm_prompt import ask_to_confirm

message = "A plain summary of what will change..."
if not ask_to_confirm(message, "My Script Title"):
    raise SystemExit("Stopped at your request. Nothing was changed.")
```

- On a Mac, `ask_to_confirm` shows a dialog with **Cancel** and **Apply**
  buttons (Apply is the default, so Return confirms). If the dialog cannot be
  shown (Databricks, Linux, or `osascript` missing), it falls back to a typed
  prompt and continues only when you type `yes`. Anything other than a clear
  yes means no.
- `confirm_prompt.py` knows nothing about roles, queues, or users. Do not add
  Genesys logic to it, and do not re-implement it in a script.

How to build the flow:

1. **Read first.** Read everything you need and change nothing. Read each
   entity once and reuse that object when you apply, so you do not fetch it
   twice.
2. **Plan without mutating.** Use a separate function that returns what would
   change (for example `plan_new_permissions_for_role`). It must make no
   mutating API calls.
3. **Preview in the terminal.** Print the full plan with `print(...)`. This is
   the complete record, because a dialog cannot scroll.
4. **Stop if nothing would change.** Print a short message and return before
   the confirm, so nobody is asked about a change of zero items.
5. **Confirm once.** Put a single confirm gate after all read-only work and
   before the first change. For multi-step scripts, that means after any
   export or checkout that does not touch live data.
6. **Apply, then summarize.** Make the changes, handling errors per item (see
   Error Handling), then print one short summary.

Writing the dialog message (build it in a `format_..._for_confirm` function):

- **Show names, not IDs.** Look names up with the shared helpers in
  `genesys_common.py` (`get_user_name`, `get_role_name`, and so on). They fall
  back to `(name unavailable)` if a read fails.
- **Put the whole plan in the dialog,** not a one-line summary. Use short,
  flat sections, such as "The following permissions will be added:" followed by
  one item per line, then a blank line, then "The following roles will receive
  the above permissions:" followed by the role names.
- **List only what will actually change,** but still show every entity in
  scope so the reader sees who is affected.
- **Spell out destructive or live effects in plain words.** Examples: "this
  REPLACES the target's current access", "the old role is removed only after
  every user is confirmed to have the new role", "Apply publishes the flow
  live".
- **Keep it short for large plans.** The dialog does not scroll. For long lists
  (such as every migrated user), show counts and the key names, and leave the
  full list to the terminal preview.
- The same message text drives both the Mac dialog and the typed fallback, so
  both show the same list.

Final summary:

- Print **one** summary, not one block per item. List what was changed once,
  then the names of the entities that actually changed. Leave out ones that
  already had everything or whose save failed.
- Word it as what happened, for example: "You have successfully added the
  following 3 permission(s) to these 2 role(s)."

Destructive and multi-step flows:

- Verify the intended end state before the irreversible step and abort
  (`raise SystemExit(1)`) if verification fails (e.g. confirm the new role is
  present on all users before removing the old role). Never silently treat a
  failed or partial job as success.
- Keep a script's existing safety checks when you change its confirm flow.

## Error Handling

- Wrap Genesys SDK calls in `try/except ApiException as e`.
- For fatal, top-level failures, `raise SystemExit("... %s" % e)` with context.
- Inside loops over many entities (users, MUs), catch per-item errors, print a
  message, and continue so one bad record doesn't abort the whole run.
- For async jobs, poll until a terminal state and raise `RuntimeError` on any
  failure or unrecognized state rather than assuming completion.

## Common Patterns

- **Pagination:** use the module helpers (`get_all_users`, `get_role_user_ids`,
  `get_queue_user_ids`) where one fits. For a new list call, loop `page_number`
  from 1, extend results from `response.entities or []`, and stop once
  `page >= (response.page_count or 0)`. If that list gets reused, move it into
  `genesys_common.py`.
- **Rate limits:** wrap busy loops of reads in `call_api(...)` from the module
  so a 429 waits and retries instead of failing.
- **Reuse the API client:** build it once via `build_apis(...)` and pass it into
  helpers; don't re-authenticate per call.
- **Output/logging:** use `print(...)` for progress and summaries, and
  `pprint(...)` for structured collections (matched users, duplicates).
- **Guard optional SDK attributes** with `getattr(obj, 'attr', None)` and
  null checks before use.

## Databricks / Local Dual-Mode Scripts

For scripts that run both locally and as Databricks notebooks (the adherence
pulls), follow these conventions:

- Mark notebook cell boundaries with `#----Cell N in Databricks----` comments.
- Keep an extensive header docstring/comment block documenting: the high-level
  flow, what runs locally vs. what is Databricks-only, and the exact steps to
  promote from local/TEST to LIVE production.
- Tag every line that differs between local and Databricks with a `LOCAL RUN:`
  comment so the toggles are greppable. Comment out Databricks-only lines
  (`spark`, `display`, `%sql`, Delta writes) for local runs.
- Detect the environment with `if "spark" not in dir():` for local-only blocks
  (e.g. CSV exports) so they stay inert in Databricks.
- Centralize the local/Databricks difference in as few places as possible
  (ideally the ENVIRONMENT CONFIG cell and auth).
- When exporting data locally, serialize list/dict columns to JSON strings so
  nested data lands cleanly in a single CSV cell (see `export_df_to_csv`).
- Keep raw landing tables append-only; use `MERGE` keyed on a stable grain for
  final tables so re-runs upsert instead of duplicating.

## Simplicity & Readability (Preferred)

Favor the simplest, most readable solution that does the job. These scripts are
maintained by people who are not full-time Python developers, so clarity beats
cleverness every time.

- Write code a reader can follow top-to-bottom without decoding it. When there
  is a choice between a clever one-liner and a few plain lines, choose the plain
  lines.
- Prefer simple `for` loops with clear variable names over dense or nested
  comprehensions. A comprehension is fine only when it is short and reads like a
  single obvious thought; if it has nested loops, multiple conditions, or wraps
  across lines, use a regular loop instead.
- Use plain, descriptive names and small functions over compact expressions.
- Favor clear, descriptive functions even if they end up a bit longer. A
  function that spells out its steps in plain, readable lines is better than a
  short one that is dense or hard to follow. Optimize for the next reader
  understanding it at a glance, not for fewer lines.
- Give functions and their parameters names that say what they do and what they
  return, so a caller rarely needs to read the body to understand them. Prefer
  an explicit sequence of named steps (with intermediate variables) over
  chaining several operations into one packed expression.
- Prefer standard library and straightforward SDK calls over advanced language
  features (metaclasses, decorators, generators, `functools`/`itertools` tricks,
  clever unpacking). Reach for an advanced technique only when the simple
  version is genuinely inadequate, and add a comment explaining why.
- Avoid premature abstraction. Don't add helpers, config layers, or generalized
  machinery until there is a concrete, repeated need.
- When you must write something non-obvious, add a short comment explaining the
  intent so the next reader doesn't have to reverse-engineer it.
- If a simple approach and an advanced one are both reasonable, default to the
  simple one and mention the tradeoff rather than silently optimizing.

## Style

- 4-space indentation, standard PEP 8 naming: `snake_case` functions/variables,
  `UPPER_SNAKE_CASE` constants.
- Prefer clear, explicit code. Keep comprehensions only when they stay short and
  obvious (see Simplicity & Readability above).
- Add comments for intent and gotchas, not for restating the code.
- Group imports: stdlib, then third-party (`pandas`, `requests`,
  `PureCloudPlatformClientV2`), then workspace modules (`confirm_prompt`,
  `genesys_common`), then Databricks/pyspark. Scripts no longer import
  `dotenv` or `os` just to sign in. Only `genesys_common.py` loads `.env`.
