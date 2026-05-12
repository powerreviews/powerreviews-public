# powerreviews-public — RepoDocs
_Generated on 2026-05-11_

## Summary

### Overview
This repository contains a single Python test script (`py/EAPI.py`) for exercising the PowerReviews **Enterprise API** — a public REST API that lets enterprise customers page through reviews and questions/answers UGC. The script is a developer/integration aid distributed publicly (per the `powerreviews-public` repo name and MIT-style license header) and demonstrates OAuth client-credentials auth, paging, server-error backoff, and basic UGC tallying (image, video, merchant-response, and answer counts) against the live `enterprise-api.powerreviews.com` endpoint. It is a standalone utility — not a service, not a library — pointed at three environments (`dev`, `qa`, `prod`).

### Tech Stack
| Category | Technology | Version |
|----------|-----------|---------|
| Language | Python | 3.x |
| Framework | requests (HTTP client) | 2.25.1 |
| Build Tool | pip / requirements.txt | N/A |
| CI/CD | _No CI/CD config detected in repo._ | N/A |
| Cloud/Infra | None (script invokes a hosted PowerReviews HTTPS endpoint) | N/A |

### Consumers
| Consumer | Type | How They Use It |
|----------|------|----------------|
| PowerReviews customers / integration partners | External developers | Public reference script for testing Enterprise API OAuth, paging, and UGC retrieval against `enterprise-api.powerreviews.com` |
| Internal QA / engineers | Org users | Smoke-test the Enterprise API across `dev-`, `qa-`, and `prod` Enterprise API hostnames |

### Dependencies on Org Repos
| Repo | Reason |
|------|--------|
| _None._ | The script imports only third-party PyPI packages and calls a hosted HTTPS endpoint; no org repos are referenced as source dependencies. |

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
| urllib3 | 1.26.5 | Multiple post-1.26.5 CVEs (e.g. CVE-2021-33503 pinned for, but later CVE-2023-43804 / CVE-2023-45803 / CVE-2024-37891 affect this branch); 1.x is well past current 2.x maintenance line | Critical |
| requests | 2.25.1 | CVE-2023-32681 (proxy-Authorization header leak) affects versions < 2.31.0 | Critical |
| certifi | 2020.12.5 | CVE-2022-23491 — bundled root certificates trust e-Tugra CA; fixed in 2022.12.7 (dependabot PR for this exists but is unmerged on HEAD) | Critical |
| idna | 3.1 | CVE-2024-3651 — denial of service via crafted input to `idna.encode()`; fixed in 3.7 | Critical |
| Python | 3.x (unpinned; README only says "Python 3.x") | Python 3.6 / 3.7 are EOL; even 3.8 reached EOL 2024-10. No minimum pin in the repo. | Severe |

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

### CI/CD tooling
_No CI/CD config detected in repo._ No `Jenkinsfile`, `.circleci/`, `.github/workflows/`, `.gitlab-ci.yml`, `.travis.yml`, `.buildkite/`, or `buildspec.yml` is present at HEAD `3d3ac06`. (Dependabot PRs do exist on the GitHub remote — a `dependabot/pip/certifi-2022.12.7` branch and a `whitesource/configure` branch — but neither is merged into the HEAD commit.)

### Test architecture
_None._ The repo contains no test files, no `tests/` directory, and no test runner config. The script itself is the test artifact — it is the thing developers run to validate the upstream API.

### Data model / database schema
_Not applicable._ The script is stateless apart from in-memory counters and a per-run `.log` file; no database, ORM, or persistent store is referenced.

### Auth & trust boundaries
- **Inbound**: none — this is a CLI invoked locally; no listening sockets, no inbound routes.
- **Outbound**: OAuth2 `client_credentials` grant against PowerReviews; client ID and secret accepted as plaintext CLI arguments and (per logging note `# print(f'c={client_id} s={client_secret}')` left as a commented debug line) never written to the log by default. The retrieved bearer token is sent in an `Authorization:` header (note: the raw access_token is placed in the header without a `Bearer ` prefix — line 130 — relying on the API to accept that form).
- **Authorization model**: delegated entirely to the PowerReviews Enterprise API; the script enforces no local authz.

### Data ownership
_Not applicable._ The script owns no datastore. The only persisted artifact is a per-run `.log` file on the local filesystem.

### Deployment topology
_Deployment topology not in this repo._ There is no Dockerfile, Helm chart, Terraform, or k8s manifest. The script is intended to be run ad-hoc on a developer machine.

## Repo Activity

Derived from git history; current HEAD is `3d3ac06`.

- **Created**: 2021-05-25 (`d96038b` — "Adding enterprise_api_reviews_paging.py")
- **Last meaningful change**: 2021-06-05 (`85ea779` — "Updating script to be more useful, accept params" — added the getopt-based CLI flags, env switching, and backoff/retry loop)
- **Activity level**: 0 commits in the last 90 days on HEAD. (Two later commits exist on un-merged remote branches: `91bd8b6` certifi bump on 2022-12-08 and `9ebd7f8` `.whitesource` config on 2026-03-23. Neither is reachable from HEAD `3d3ac06`.)
- **Hot spots** (last 6 months, on HEAD): _None — no commits on HEAD in the last 6 months._ Across the entire history of HEAD, the only churn is `py/EAPI.py` (3 commits) and `requirements.txt` (2 commits).
- **Recent major changes**: _No major changes in the last 6 months._ The repository has been effectively dormant since 2021-06-05; only un-merged dependabot/whitesource activity exists after that on the remote.
