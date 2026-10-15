# Python Scripting Standards (Coding Workspace)

These standards are derived from the existing scripts in `src/` (Genesys Cloud
automation and Databricks adherence pulls). Follow them when writing or editing
Python in this workspace so new scripts match the established conventions.

## Domain & Stack

- All scripts automate **Genesys Cloud** via the official SDK
  `PureCloudPlatformClientV2` (pinned in `requirements.txt`).
- Runtime dependencies live in `requirements.txt` with **pinned versions**
  (e.g. `PureCloudPlatformClientV2==266.0.0`, `python-dotenv==1.0.1`). Pin any
  new dependency you add.
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
- Standardize authentication in a `build_apis()` function that:
  1. Loads `.env` relative to the script:
     `load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))`
  2. Reads client id/secret via `os.environ.get(...)`.
  3. Raises `SystemExit` with a helpful message if either is missing
     (point the user at copying `.env.example` to `.env`).
  4. Returns only the specific API client(s) the script needs
     (e.g. `AuthorizationApi`, `UsersApi`, `WorkforceManagementApi`).
- Authenticate with client credentials:
  `PureCloudPlatformClientV2.api_client.ApiClient().get_client_credentials_token(client_id, client_secret)`.
- In Databricks, swap the `.env`/`os.environ` lookups for a secrets scope,
  e.g. `dbutils.secrets.get(scope="purecloud", key="clientId")`. Keep this the
  only spot that changes between local and Databricks auth.

## Script Structure

- Order every script: module docstring → imports → configuration constants →
  `build_apis()` / setup → helpers → step functions → `main()`.
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

## Configuration Conventions

- Put all tunables in a configuration block near the top of the file as
  module-level constants in `UPPER_SNAKE_CASE`
  (`PAGE_SIZE`, `DIVISION_SUFFIX`, `INCREMENTAL_LOOKBACK_DAYS`,
  `ADHERENCE_TIME_ZONE`, `TABLE_*`).
- Keep lakehouse/table names as constants used as the single source of truth
  (e.g. `TABLE_BUSINESS_UNITS = "wgu_lakehouse.genesys.stg_business_units"`).
- Explain non-obvious config with an inline comment right above it.

## Safety: DRY_RUN for Mutations

- Any script that **modifies** Genesys state (grant/remove roles, delete,
  bulk update) must expose a module-level `DRY_RUN` flag, defaulting to `True`.
- When `DRY_RUN` is `True`, perform reads only and print the intended changes
  with a `[DRY-RUN]` prefix; make no API calls that mutate state.
- For destructive multi-step flows, verify the intended end state before the
  irreversible step and abort (`raise SystemExit(1)`) if verification fails
  (e.g. confirm the new role is present on all users before removing the old
  role). Never silently treat a failed/partial job as success.

## Error Handling

- Wrap Genesys SDK calls in `try/except ApiException as e`.
- For fatal, top-level failures, `raise SystemExit("... %s" % e)` with context.
- Inside loops over many entities (users, MUs), catch per-item errors, print a
  message, and continue so one bad record doesn't abort the whole run.
- For async jobs, poll until a terminal state and raise `RuntimeError` on any
  failure or unrecognized state rather than assuming completion.

## Common Patterns

- **Pagination:** loop `page_number` from 1, extend results from
  `response.entities or []`, and stop once `page >= (response.page_count or 0)`.
- **Reuse the API client:** build it once via `build_apis()` and pass it into
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
  `PureCloudPlatformClientV2`, `dotenv`), then Databricks/pyspark.
