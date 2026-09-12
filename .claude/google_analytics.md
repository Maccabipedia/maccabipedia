# Google Analytics

How MaccabiPedia's traffic data is collected, and how to query it from Claude Code.

## Collection (on the wiki)

The wiki tags pages via the **GTag** extension, not the retired Google Analytics
Integration extension:

- `wfLoadExtension('GTag')` — `infra/local-wiki/config/LocalSettings.shared.php`
- `$wgGTagAnalyticsId` is set **per environment**, never in `shared.php`:
  - `LocalSettings.env.local.php` sets it to `''` so dev never pollutes prod data
  - prod's value lives in `LocalSettings.env.prod.php`, which is not in this repo
- The extension is SHA-pinned in `infra/local-wiki/extensions.json` (v1.4.0;
  master requires MW >= 1.43, we are on 1.39)

A commented-out `$wgGoogleAnalyticsAccount = 'UA-...'` remains in `shared.php`.
That is Universal Analytics, which stopped collecting in July 2023. Ignore it.

## Querying (from Claude Code)

The official Google server — [`googleanalytics/google-analytics-mcp`][repo],
PyPI `analytics-mcp` — is wired into `.mcp.json` as `google-analytics`:

```json
"google-analytics": {
  "command": "uv",
  "args": ["tool", "run", "--from", "analytics-mcp", "analytics-mcp"],
  "env": {
    "GOOGLE_APPLICATION_CREDENTIALS": "<path to the service account JSON>",
    "GOOGLE_PROJECT_ID": "<gcp project>"
  }
}
```

Launch with `uv tool run`, **not** `pipx` — the README says pipx, but pipx is not
installed on this box and `uv` is the repo standard anyway.

Tools: `run_report`, `run_realtime_report`, `run_funnel_report`,
`run_conversions_report`, `get_account_summaries`, `get_property_details`,
`get_custom_dimensions_and_metrics`, `list_property_annotations`,
`list_google_ads_links`. The server is read-only by design — there are no write
tools, and the credential carries only `analytics.readonly`.

### Credentials

A **service account**, following the same store as the YouTube credentials:
`~/.config/maccabipedia/` (mode 0700, each file 0600). See
`.claude/maccabipedia_youtube_channel.md` for the sibling files.

The service account has **zero GCP IAM roles**. All of its access comes from
being added as a **Viewer** on the GA4 property itself
(GA Admin → Property → Property access management). Grant at *property* level,
never account level — account level would expose every property under the
account. Revoking the property grant fully revokes the credential.

`.mcp.json` is gitignored and carries only the *path* to the key. The key never
enters the repo. `.claude/hooks/create-worktree.sh` copies `.mcp.json` from the
repo root into each new worktree, so adding a server to the main checkout's copy
is enough — existing worktrees keep their old copy until recreated.

### Properties

GA4 account `123078340` (the same account as the old UA property) holds two
GA4 properties, both recording near-identical traffic:

| Property | Name | Created | Use |
|---|---|---|---|
| `351108230` | MaccabiPedia ‎ - GA4 | 2023-01-26 | **use this one** — actively maintained |
| `267860787` | MaccabiPediaGA4 | 2021-04-04 | untouched since creation |

Only one measurement ID appears in the prod HTML, so the second property is most
likely fed by GA connected-site-tags forwarding. That is a hypothesis — the MCP
exposes no data-stream tool, so confirm in GA Admin → Data streams before
relying on it.

[repo]: https://github.com/googleanalytics/google-analytics-mcp
