# powerreviews-public — RepoDocs
_Generated on 2026-05-11 · Consolidated on 2026-05-19 against commit 704d41c_

## Summary

### Overview
`powerreviews-public` is the org's only externally distributed code artifact: a single Python reference script (`py/EAPI.py`) that demonstrates OAuth2 client-credentials auth, cursor-based paging, exponential backoff, and adaptive `limit` shrinking against the PowerReviews **Enterprise API** (`enterprise-api.powerreviews.com`). It is consumed by enterprise customers / integration partners learning how to pull reviews and Q&A UGC programmatically; the upstream API itself is served by the org's `enterprise-services` (Kotlin/Spring Boot, syndication-db backed) — this repo is a thin client *to* that service, not a component *of* it. Within the org it is a CLI Tools repo (per the org catalog), pairs conceptually with `pwr-scripts` (which also has internal "EAPI tasks"), and is structurally unrelated to the same-named-prefix `powerreviews-pufferfish` legacy monolith. The minimum credential set a partner needs to use this script is the two EAPI read scopes `b2b-api/reviews.read` and `b2b-api/questions.read`; the script accepts `client_id`/`client_secret` as runtime arguments because secrets are stored only in AWS Cognito and never embedded as defaults.

### Tech Stack
| Category | Technology | Version |
|----------|-----------|---------|
| Language | Python | 3.x (unpinned) |
| Framework | requests + getopt (stdlib CLI) | requests 2.25.1 |
| Database | None | N/A |
| Build Tool | pip / requirements.txt | N/A |
| CI/CD | None on HEAD (Mend/WhiteSource + Dependabot configured on unmerged remote branches only) | N/A |
| Cloud/Infra | None (script targets a hosted HTTPS endpoint owned by `enterprise-services`) | N/A |

### Consumers
| Consumer | Type | How They Use It |
|----------|------|----------------|
| PowerReviews enterprise customers / integration partners | External developers | Public reference for implementing OAuth2 + paging against `enterprise-api.powerreviews.com` (the only public-facing repo in the org alongside `corpsite`, `Documentation-Output`, `api-documentation`) |
| Internal QA / SE / support engineers | Org users | Ad-hoc smoke testing of the Enterprise API across `dev-`, `qa-`, and `prod` hostnames |
| `enterprise-services` team | Org service team | Indirect — the script exercises their public surface and serves as customer-facing usage documentation |

### Dependencies on Org Repos
| Repo | Reason |
|------|--------|
| `enterprise-services` | Runtime upstream — script exclusively calls `enterprise-api.powerreviews.com/v1/{reviews,questions}` and `/oauth2/token`, which is the public B2B Kotlin/Spring Boot service backed by syndication-db. No source-level coupling, but the API contract (paging cursor `next_page`, `count`, `media[].type`, `merchant_responses[]`) is owned by that repo. |
| `pwr-scripts` | Conceptual overlap — the org catalog describes `pwr-scripts` as containing "ad-hoc Python ops scripts for ... EAPI tasks." Likely the internal-facing twin of this public script; any drift in the EAPI contract is felt in both. Confluence's `EAPI Tools: Get Reviews` page corroborates this directly, describing a newer `get_reviews.py` (Python 3.11+, `httpx`, DuckDB, dotenv) in `pwr-scripts` as the recommended/current EAPI reference tool. |
| `denormalization-services` / `syndication-db` ecosystem | Indirect data lineage — the reviews/questions returned upstream originate from `core-data-services` → SNS `pwr-event-log` → `denormalization-services` → `syndication-db`, which `enterprise-services` reads from. Not a source dependency, but explains the data the script counts. |
| `whitesource-config` | Org-wide Mend scan policy — referenced on the unmerged `whitesource/configure` remote branch (not on HEAD `494840e`). |

### External Integrations
| Service | Purpose | Integration Type |
|---------|---------|-----------------|
| PowerReviews Enterprise API (`enterprise-api.powerreviews.com`, `dev-` and `qa-` variants) | Fetch reviews / questions UGC, including media, syndication, and merchant responses | REST |
| PowerReviews OAuth2 token endpoint (`/oauth2/token` on the same host) | Obtain bearer token via `client_credentials` grant for the REST calls above | OAuth |

### Async & Scheduled Work
_No async or scheduled work detected._

### Upgrade Alerts
| Dependency | Current Version | Issue | Severity |
|-----------|----------------|-------|----------|
| requests | 2.25.1 | CVE-2023-32681 — Proxy-Authorization header leak on redirect; fixed in 2.31.0. Especially severe here because this is a script *published to external partners* — every consumer inherits the CVE. | Critical |
| urllib3 | 1.26.5 | CVE-2023-43804 / CVE-2023-45803 (Cookie / Authorization header leak across redirects) and CVE-2024-37891 (proxy auth) all post-date the pinned version on the 1.x branch. | Critical |
| certifi | 2020.12.5 | CVE-2022-23491 — bundled e-Tugra root trust; fixed in 2022.12.7. A dependabot bump PR exists on the remote but is unmerged on HEAD. | Critical |
| idna | 3.1 | CVE-2024-3651 — DoS via crafted `idna.encode()` input; fixed in 3.7. | Critical |
| Python runtime | 3.x unpinned (README says "Python 3.x") | 3.6/3.7/3.8 all EOL; no minimum version pin. Script uses 3.6+ f-strings and `time.time_ns()` (3.7+) but does not declare it. | Severe |
| Repo maintenance | HEAD last touched 2021-06-05; Dependabot/WhiteSource branches stranded unmerged for years | EOL-by-neglect — the public-facing example is effectively abandoned while CVEs accumulate. | Severe |

### Coupling Profile
| Dependency | Protocol | Frequency Pattern | Failure Mode |
|-----------|----------|-------------------|--------------|
| `enterprise-services` `/v1/{reviews,questions}` | sync HTTP (REST, JSON, single-connection `requests.Session` with `pool_maxsize=1`) | per-request, sequential paging up to `--max_pages`, no parallelism | soft on 5xx (exponential backoff 1→256 s, adaptive `limit` halving toward 1, doubling back toward `MAX_LIMIT=100` on success); soft on 401 (single re-auth retry); hard once `BACKOFF_TIME_LIMIT=256s` is exceeded (raises) |
| `enterprise-services` `/oauth2/token` | sync HTTP (OAuth2 `client_credentials`, HTTP Basic) | startup-only, plus on-demand re-auth on a mid-paging 401 | hard — non-200 raises immediately; blank `client_id`/`client_secret` raises before request |
| Local filesystem (per-run `.log` file) | file/object store (local fs) | per-invocation | hard — Python logging will surface IOError, but no recovery; `.log` files are git-ignored |

Notes worth flagging for an architect:
- The `Authorization:` header is set to the raw `access_token` **without a `Bearer ` prefix** (line 130). If `enterprise-services` ever tightens RFC 6750 compliance, every external customer who copy-pasted this reference breaks. This is a public-facing contract risk, not an internal one.
- Coupling is purely contract-level (no shared DB, no shared queue, no shared library) — the cheapest possible coupling, but invisible to internal refactors of `enterprise-services` unless they consider the published example.

### Architectural Notes
- **Shared infrastructure**: None directly. The data the script consumes flows through the heavily shared infrastructure called out in the org summary — `syndication-db` Postgres (consumed by `denormalization-services`, `distribution-services`, `enterprise-services`, `db-syndication-ad-hoc-migrations`) and the `pwr-event-log` SNS topic that fans out from `core-data-services` — but this repo touches none of it directly.
- **Bounded-context overlaps**: The response shape it parses (`reviews[]`, `questions[]`, nested `media[].type`, `merchant_responses[]`, `count`, `next_page`) is the canonical Enterprise API surface, which is itself a projection of the UGC domain owned by `core-data-services` / `pwr-data-model`. The string-typed `media.type` enum the script branches on (`image`/`video`/`answer`) is mirrored in `pwr-data-model` and `pwr-js-utils`; any rename there silently breaks this client.
- **Public-surface positioning**: Within the 227-repo catalog this is one of only ~4 truly external-facing artifacts (with `corpsite`, `Documentation-Output`, `api-documentation`). It is the *only* one shipping executable example code to customers, which materially raises the bar for the unpatched CVEs above.
- **Architectural evolution**: Git history shows two bursts only — initial drop on 2021-05-25 (single-file script), CLI/backoff polish on 2021-06-05 (`85ea779`), then dormancy. Subsequent activity is entirely automated: a 2022-12 Dependabot certifi bump and a 2026-03 WhiteSource config commit, both stranded on unmerged remote branches. Effectively orphaned: no owner has merged maintenance in 4+ years despite the repo being public and externally consumed.
- **Diverging from internal twin**: The internal `get_reviews.py` in `pwr-scripts` has continued to evolve (Python 3.11+, `httpx`, DuckDB, dotenv, broad parameter coverage including `created_date`, `updated_date`, `pwr_publication_status`, `client_publication_status`, `user_id`, `disclosure_inline`, `legacy_id`, `include_filter_effective_dates`, `include_upc`, etc.), while this public sample is stuck on `requests` 2.25.1 and a small hard-coded subset of parameters. The two reference tools are diverging. The internal tool also deliberately caches tokens past their 1-hour expiry to save Cognito cost (requires VPN); the public script correctly does not — it just re-auths on 401, which is the appropriate behaviour for external partners.
- **Known upstream quirk worth surfacing to integrators**: PWRE-2818 confirms EAPI's `updated_date` / `created_date` filters silently drop the time component (treated as midnight) and `include_filter_effective_dates` is currently a no-op. Any partner extending `py/EAPI.py` to add these filters should be aware that "after 17:15 UTC today" effectively becomes "after 00:00 UTC today" until the bug is fixed upstream.
- **Naming collision risk**: Do not confuse this repo with `powerreviews-pufferfish` (the legacy Java/Spring/Hibernate monolith) — the names share a prefix but the repos have zero relationship in code, ownership, or runtime.

## API Reference

This repo is a CLI script, not a service. It has no public HTTP surface; its "API" is its command-line flags, internal functions, and the upstream HTTP endpoints it calls.

### Command-line invocation
`python py/EAPI.py [--client_id=...] [--client_secret=...] [--endpoint=...] [--max_pages=...] [--env=...]`

| Flag | Type | Default | Allowed values | Purpose |
|------|------|---------|----------------|---------|
| `--client_id` | string | `''` (required at runtime) | any | OAuth2 client ID — `Exception` raised if blank |
| `--client_secret` | string | `''` (required at runtime) | any | OAuth2 client secret — `Exception` raised if blank |
| `--endpoint` | string | `'reviews'` | `reviews`, `questions` (anything else is coerced to `reviews`) | Which Enterprise API resource to page |
| `--max_pages` | int | `1` | non-negative int (negatives coerced to `1`) | Upper bound on pages fetched |
| `--env` | string | `'dev'` | `dev`, `qa`, `prod` (anything else coerced to `dev`) | Selects `dev-enterprise-api…`, `qa-enterprise-api…`, or `enterprise-api.powerreviews.com` |

### Internal functions (`py/EAPI.py`)
- `get_access_token() -> str` (line 110) — POSTs to `<protocol><domain>/oauth2/token` with `grant_type=client_credentials` and HTTP Basic auth (`client_id`, `client_secret`); returns `access_token` from the JSON body. Raises if either credential is empty or the response status ≠ 200.
- `page_ugc(parameters: dict) -> None` (line 126) — Drives the paging loop against `<protocol><domain>/v1/<endpoint>` up to `max_pages`. Features: per-request timing, exponential backoff (start 1 s, doubling up to `BACKOFF_TIME_LIMIT = 256` s) on HTTP 5xx, automatic `limit` halving on 5xx and doubling back toward `MAX_LIMIT = 100` on success, re-auth on HTTP 401, and `next_page` cursor handling. Mutates a large set of module-level aggregate counters.
- `get_child_ugc_count(ugcs: list) -> tuple` (line 217) — Walks the response list of reviews or questions and returns `(image_count, video_count, merchant_response_count, answer_count)`. Image/video/answer come from inspecting each item's `media[].type`; merchant responses come from `len(item['merchant_responses'])`.

### Upstream HTTP calls
- `POST https://[dev-|qa-|]enterprise-api.powerreviews.com/oauth2/token` (form-encoded, HTTP Basic) → `{access_token: …}`
- `GET https://[dev-|qa-|]enterprise-api.powerreviews.com/v1/{reviews|questions}` with query params `include_media=true`, `include_syndication=true`, `include_merchant_responses=true`, `limit`, optional `next_page`, and an `Authorization` header carrying the raw token returned by the OAuth call. Response shape consumed: `{count, reviews|questions: [...], next_page?}`.

### Constants
`PROTOCOL='https://'`, `MAX_LIMIT=100`, `BACKOFF_TIME_LIMIT=256`.

## Architecture

### System context

```
+-----------------+         CLI flags           +-------------------+
|   Developer /   |  --client_id --secret ...   |    py/EAPI.py     |
|  QA engineer    +---------------------------->|  (Python script)  |
+-----------------+                             +---------+---------+
                                                          |
                                          POST /oauth2/token (Basic auth)
                                                          v
                                            +-----------------------------+
                                            | PowerReviews Enterprise API |
                                            | [dev-|qa-|]enterprise-api.  |
                                            |   powerreviews.com          |
                                            +-----------------------------+
                                                          ^
                          GET /v1/reviews | /v1/questions |
                          + Authorization header,         |
                          + paging via next_page cursor   |
                                                          |
                                                  Local log file:
                                                  EAPI__<env><ep>...<ns>.log
```

### Key components
- **Arg parsing** (`getopt`, lines 35–66): tolerant — invalid values silently coerce to defaults rather than fail.
- **Logging** (lines 68–78): logs to both stdout (`StreamHandler`) and a file named from script-name + env + endpoint + client_id + `time.time_ns()`. `.log` files are git-ignored via `.gitignore`.
- **Auth helper** (`get_access_token`): re-invoked on 401 mid-paging to refresh the token.
- **Paging engine** (`page_ugc`): wraps the GET in a `requests.Session` with a pool size of 1; combines retry/backoff and adaptive `limit` shrinking on 5xx into one loop.
- **Aggregation** (`get_child_ugc_count` + module-level counters): tallies images/videos/merchant-responses/answers for the final summary log.

### Data flow
1. CLI args parsed → env-prefixed domain + endpoint URL constructed.
2. `page_ugc` runs the paging loop: fetch OAuth token → GET page → on 5xx, sleep + halve `limit` and retry; on 401, refresh token and retry; on 200, accumulate counters and follow `next_page` until absent or `max_pages` reached.
3. End-of-run summary logged: total time, wait time, per-request avg/min/max, total UGC counts, timeout count, minimum `limit` reached.

### Upstream EAPI security model
The upstream Enterprise API places **all** OAuth2 bearer token verification at the AWS API Gateway / Cognito layer — downstream Java services do not check the access token or roles. From the Gateway, EAPI requests fan out to (a) Lambdas for account-management ops, (b) Product Service for product calls, (c) Core Data Services for reads, (d) Write Services for writes. The two endpoints the public script exercises (`/v1/reviews`, `/v1/questions`) are served by the Core Data Services read path, which is consistent with the data-lineage note above (`core-data-services` → `denormalization-services` → `syndication-db`). Because token validation is centralised at the Gateway, this script's only correct response to a 401 is to request a brand-new token (no refresh-token flow exists; tokens expire after 3,600 s) — which is exactly what `page_ugc` does. The OAuth2 host family `b2b-api.powerreviews.com` is documented as equivalent to `enterprise-api.powerreviews.com` across `dev`/`qa`/`prod`; the script uses the `enterprise-api` variant. Admin OAuth client IDs are public (per docs); secrets live only in Cognito, which is why the script demands them as runtime arguments rather than embedding defaults.

### CI/CD tooling
_No CI/CD config detected in repo._ No `Jenkinsfile`, `.circleci/`, `.github/workflows/`, `.gitlab-ci.yml`, `.travis.yml`, `.buildkite/`, or `buildspec.yml` is present at HEAD `3d3ac06`. (Dependabot PRs do exist on the GitHub remote — a `dependabot/pip/certifi-2022.12.7` branch and a `whitesource/configure` branch — but neither is merged into the HEAD commit.)

### Test architecture
_None._ The repo contains no test files, no `tests/` directory, and no test runner config. The script itself is the test artifact — it is the thing developers run to validate the upstream API.

### Data model / database schema
_Not applicable._ The script is stateless apart from in-memory counters and a per-run `.log` file; no database, ORM, or persistent store is referenced.

### Auth & trust boundaries
- **Inbound**: none — this is a CLI invoked locally; no listening sockets, no inbound routes.
- **Outbound**: OAuth2 `client_credentials` grant against PowerReviews; client ID and secret accepted as plaintext CLI arguments and (per logging note `# print(f'c={client_id} s={client_secret}')` left as a commented debug line) never written to the log by default. The retrieved bearer token is sent in an `Authorization:` header (note: the raw access_token is placed in the header without a `Bearer ` prefix — line 130 — relying on the API to accept that form).
- **Authorization model**: delegated entirely to the PowerReviews Enterprise API; the script enforces no local authz. The minimum scopes a partner needs are `b2b-api/reviews.read` and `b2b-api/questions.read`; administrator scope `b2b-api/accounts.lambda` (used for client-app CRUD via `/v1/create-client-app`, `/v1/lookup-client-app-by-id`, `/v1/lookup-client-app-by-mgid`, `/v1/delete-client-app`, `/v1/modify-client-app`, `/v1/toggle-disable-client-app`) is **not** exercised by this script.

### Data ownership
_Not applicable._ The script owns no datastore. The only persisted artifact is a per-run `.log` file on the local filesystem.

### Deployment topology
_Deployment topology not in this repo._ There is no Dockerfile, Helm chart, Terraform, or k8s manifest. The script is intended to be run ad-hoc on a developer machine.

## Documentation Discrepancies

| Confluence States | Code Shows | Likely Reason |
|------------------|-----------|---------------|
| `"token_type": "Bearer"` — i.e. EAPI issues Bearer tokens, implying the standard RFC 6750 `Authorization: Bearer <token>` form. | `py/EAPI.py:130` sets `Authorization` to the **raw `access_token` with no `Bearer ` prefix**. | Outdated doc / shortcut accepted historically by the API Gateway. The public sample bakes in a non-standard header form that every external partner inherits. |
| `EAPI Tools: Get Reviews` says the recommended/current EAPI reference tool is `get_reviews.py` in `pwr-scripts` — Python 3.11+, `httpx`, DuckDB, broad parameter coverage, last updated 2026-05-04. | This repo's `py/EAPI.py` uses Python 3.x (unpinned), `requests` 2.25.1, no local DB, supports only a small subset of EAPI parameters (`include_media`, `include_syndication`, `include_merchant_responses` hard-coded `true`; no support for filters such as `created_date`, `updated_date`, `merchant_id`, publication-status flags). HEAD last touched 2021-06-05. | Scope split — the internal tool has continued to evolve in `pwr-scripts`, while the public repo has been effectively abandoned. The two are diverging. |
| PWRE-2818: EAPI's `updated_date` / `created_date` filters use only the date portion (midnight) and `include_filter_effective_dates` is currently a no-op. | `py/EAPI.py` does not expose any date filters or `include_filter_effective_dates` to begin with — so the public sample silently sidesteps a bug consumers would otherwise hit when they extend it. | Feature not yet built in the public sample; the bug is a property of the upstream EAPI surface, not this script. Worth flagging to external integrators relying on date filters. |
| Confluence references `oauth_client_id` / scope management (`/v1/create-client-app`, etc.) on the EAPI host. | Script reads only `/v1/reviews` and `/v1/questions`; no account-management calls. | Scope of script is intentionally narrower than EAPI's surface — not a contradiction, but a reminder that the docs describe a much larger API than this sample touches. |

## Repo Activity

Derived from git history; current HEAD is `3d3ac06`.

- **Created**: 2021-05-25 (`d96038b` — "Adding enterprise_api_reviews_paging.py")
- **Last meaningful change**: 2021-06-05 (`85ea779` — "Updating script to be more useful, accept params" — added the getopt-based CLI flags, env switching, and backoff/retry loop)
- **Activity level**: 0 commits in the last 90 days on HEAD. (Two later commits exist on un-merged remote branches: `91bd8b6` certifi bump on 2022-12-08 and `9ebd7f8` `.whitesource` config on 2026-03-23. Neither is reachable from HEAD `3d3ac06`.)
- **Hot spots** (last 6 months, on HEAD): _None — no commits on HEAD in the last 6 months._ Across the entire history of HEAD, the only churn is `py/EAPI.py` (3 commits) and `requirements.txt` (2 commits).
- **Recent major changes**: _No major changes in the last 6 months._ The repository has been effectively dormant since 2021-06-05; only un-merged dependabot/whitesource activity exists after that on the remote.
