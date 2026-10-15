---
inclusion: auto
name: Genesys Cloud SDK Reference
description: Reference links and lookup guidance for the Genesys Cloud Platform Python SDK (PureCloudPlatformClientV2) and REST API. Activate whenever the work involves Genesys Cloud APIs, the Python SDK, API clients (UsersApi, WorkforceManagementApi, AuthorizationApi, etc.), models, or REST endpoints.
---

# Genesys Cloud SDK Reference

Use these references whenever you are writing or editing code that calls Genesys
Cloud APIs. Prefer them over guessing method names, model fields, parameters, or
endpoint paths — the SDK surface is large and the exact names matter.

## Primary Reference: the SDK GitHub repo (fetchable Markdown)

The rendered docs site (https://mypurecloud.github.io/platform-client-sdk-python/)
is JavaScript-rendered and cannot be fetched as text — its pages come back empty
or 404. **Do not rely on it for lookups.** Instead, read the same content from
the SDK's GitHub source repo, which is plain Markdown/JSON:

- **Repo:** `MyPureCloud/platform-client-sdk-python` (branch `master`)
- **Per-API client docs** — one Markdown file per API, with method signatures,
  parameters, return types, and examples:
  ```
  https://raw.githubusercontent.com/MyPureCloud/platform-client-sdk-python/master/build/docs/<ApiName>.md
  ```
  Examples: `UsersApi.md`, `WorkforceManagementApi.md`, `AuthorizationApi.md`,
  `RoutingApi.md`, `AnalyticsApi.md`.
- **Per-model docs** — one Markdown file per model/data class, same folder:
  ```
  https://raw.githubusercontent.com/MyPureCloud/platform-client-sdk-python/master/build/docs/<ModelName>.md
  ```
  Examples: `User.md`, `Queue.md`, `AuthzDivision.md`.
- **Auth & usage patterns:** the repo `README.md`:
  ```
  https://raw.githubusercontent.com/MyPureCloud/platform-client-sdk-python/master/README.md
  ```
- **List/discover exact doc file names** when you are unsure of the spelling
  (returns a JSON directory listing):
  ```
  https://api.github.com/repos/MyPureCloud/platform-client-sdk-python/contents/build/docs
  ```

The raw `<ApiName>.md` / `<ModelName>.md` files are the fastest reliable source
for method names, parameters, and model fields.

## Secondary Reference: REST API Explorer

- **API Explorer / REST docs:** https://developer.genesys.cloud/devapps/api-explorer
  - Use to confirm the REST endpoint, request/response shape, query parameters,
    and required OAuth scopes/permissions behind an SDK method.
  - Also JavaScript-rendered, so it is for human browsing, not fetching. When
    you need the REST contract programmatically, the SDK repo also contains the
    full OpenAPI spec at `swagger.json` (root of the repo) — but it is very large
    (~23 MB), so use it only for narrow, targeted lookups, never a bulk read.

## Version Note

The workspace pins `PureCloudPlatformClientV2==267.0.0` in `requirements.txt`.
The repo `master` docs track the latest release, which may be slightly ahead.
If a method or field in the docs looks new, check `releaseNotes.md` in the repo
before assuming it exists in 267.0.0.

## How to Look Things Up

- **Method name / signature:** Find the relevant `*Api` class in the SDK docs
  (named after the domain, e.g. users → `UsersApi`, WFM →
  `WorkforceManagementApi`, roles/permissions → `AuthorizationApi`). Confirm the
  exact method name, parameter order, and whether params are positional or
  passed via a request/body object.
- **Model fields:** SDK models are separate classes (e.g. `User`, `Queue`,
  `AuthzDivision`). Check the model page for exact attribute names before
  reading or setting them. Guard optional attributes with
  `getattr(obj, 'attr', None)` per the workspace Python standards.
- **REST endpoint / scopes:** When unsure which SDK call maps to an endpoint, or
  what permissions it needs, look it up in the API Explorer by resource path.

## Workspace Conventions Reminder

- Authenticate once via `build_apis()` using client credentials
  (`get_client_credentials_token`) and return only the specific `*Api` clients a
  script needs. Do not re-authenticate per call.
- Wrap SDK calls in `try/except ApiException as e`; for fatal top-level failures
  raise `SystemExit`, and inside loops catch per-item errors and continue.
- Use the standard pagination pattern: loop `page_number` from 1, extend from
  `response.entities or []`, stop once `page >= (response.page_count or 0)`.
- Any script that mutates Genesys state must honor the `DRY_RUN` flag.

(See `python-scripts.md` for the full Python standards; this file only adds the
external SDK/API reference links and lookup guidance.)
