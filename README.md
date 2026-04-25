# Kantata Assist

Kantata Assist is a small Python toolkit for [Kantata OX](https://developer.kantata.com/kantata/specification) (formerly Mavenlink): a **CLI** (`kantata`) and a **stdio MCP server** (`kantata-mcp`) so people can work with projects, tasks, time, time off, and activity from the terminal or from AI tools such as Cursor.

This project is **not** affiliated with or endorsed by Kantata. It uses Kantata’s public **REST API v1** only. License: [MIT](LICENSE). Security reporting: [SECURITY.md](SECURITY.md).

---

## 1. For Kantata and account administrators

This section is for whoever controls Kantata OX **account settings**, **OAuth applications**, and **API access** so your organization can safely enable Kantata Assist.

### What you are enabling

Kantata Assist acts **on behalf of whichever user signs in** (OAuth) or whichever token you configure (bearer). It does not add Kantata permissions beyond what that user already has in Kantata. Plan rollout around **least privilege** and **who may use API access**.

### Create an OAuth application (typical rollout)

1. In Kantata OX, open **OAuth application** management (often under account or developer settings). Kantata documents this flow in their help center, for example [How to Register OAuth Applications in Kantata OX](https://knowledge.kantata.com/hc/en-us/articles/360057953073-How-to-Register-OAuth-Applications-in-Kantata-OX).
2. Create an application your users will authorize. You will receive a **client ID** and **client secret**. Treat the secret like a password.
3. Register **exactly** the redirect URI your users will use for local login. Kantata Assist defaults to:

   **`http://127.0.0.1:8765/callback`**

   Use **`127.0.0.1`**, not `localhost`, unless you deliberately standardize on `localhost` and register that variant in Kantata as well.

4. If users cannot share port **8765** (firewall or conflict), they may run login on another port; each distinct port needs its **own** redirect URI registered in Kantata (for example `http://127.0.0.1:8899/callback`). Document the port you standardize on for your org.

### Redirect URI and local callback

Kantata Assist runs a **short-lived HTTP server on the user’s machine** only during `kantata login`. The browser is sent to Kantata; after consent, Kantata redirects to that local URL with an authorization **code**, which the tool exchanges for tokens. No Kantata-hosted callback URL is required beyond what you register as the redirect URI above.

### Bearer tokens instead of OAuth (optional)

Some organizations prefer not to distribute an OAuth client secret to every user. If Kantata or your SSO flow provides a **user API token** (or similar) that is acceptable under your policy, users can set **`KANTATA_ACCESS_TOKEN`** and never run `kantata login`. You remain responsible for how that token is issued, rotated, and revoked.

### Org-hosted OAuth (Google Apps Script) (optional)

To keep the **client id and client secret off end-user machines**, you can host the authorization-code exchange in a **Google Apps Script** project deployed as a **Web app**:

1. Create a Kantata OAuth application as above, but register the **Web app URL** (from **Deploy** in Apps Script) as the **only** redirect URI you use for this flow—**exactly** as shown by Google (often `https://script.google.com/.../exec`).
2. Store **`KANTATA_CLIENT_ID`**, **`KANTATA_CLIENT_SECRET`**, and **`KANTATA_REDIRECT_URI`** (same URL) in **Project settings → Script properties**. Only people who can edit the script should see the secret.
3. The script redirects users to Kantata’s authorize URL, receives the **`code`** on redirect, POSTs to **`https://app.mavenlink.com/oauth/token`**, and shows JSON with **`access_token`** and **`token_type`** for the user to import locally.

A reference script is in [`extras/kantata-oauth-webapp/Code.gs`](extras/kantata-oauth-webapp/Code.gs). Users run **`kantata import-credentials`** (see section 2) to write `~/.config/kantata/credentials.json` from that JSON.

**If the browser shows “refused to connect” to Kantata** (DevTools HAR: request to `app.mavenlink.com` with **status 0**, **Referer** from `*.googleusercontent.com`): the Web App is running inside Google’s **sandbox iframe**. Redirecting with `window.location` only replaces that iframe; Kantata’s login must open in the **full tab** (`window.top` / `target="_top"`). Copy the latest [`Code.gs`](extras/kantata-oauth-webapp/Code.gs) into your project and **redeploy** the Web app.

Per Kantata’s API documentation, OAuth **access tokens do not time-expire** until the user revokes the application; the **authorization code** is short-lived (exchange it within a few minutes).

### Governance checklist

- **Roles:** Confirm who may create OAuth apps and use the API (often account administrators). See Kantata’s [API overview](https://knowledge.kantata.com/hc/en-us/articles/202811760-Kantata-API-Overview).
- **Secrets:** Do not put client secrets or bearer tokens in source control, screenshots, or broad chat logs. Prefer a password manager or internal secret store for distributing the OAuth pair to trusted users.
- **Rate limits:** Kantata applies [API rate limits](https://knowledge.kantata.com/hc/en-us/articles/9698066628123); heavy automation should be paced and monitored.
- **Support:** Decide whether users file tickets with **you** (internal IT) or with the maintainers of this open-source repo for tool bugs.

### What to give each user

At minimum, users who will use **local** OAuth (`kantata login`) need:

- **Client ID** and **client secret** for the app you registered (unless you use a different org-wide pattern they already have).
- The **redirect URI** (and port) they must register or that you pre-registered.
- Optional: non-default **API base** if your tenant uses a different host than the tool default (`https://api.mavenlink.com/api/v1`), via **`KANTATA_API_BASE`**.

If you use **Google Apps Script** (or another org-hosted exchange), users need only the **bookmark URL** for that web app and the **`kantata import-credentials`** steps in section 2—not the client secret.

Users who will use only a **bearer token** need the token (and rotation procedure), not the OAuth pair.

---

## 2. For users installing Kantata Assist

This section is for **you** if you want the CLI and/or MCP server on your computer.

### TL;DR

1. **Pick how you get the tools** — Easiest: **Option A** (`uvx` from git, no clone). Or **Option B** (clone the repo and install into a venv). Both are spelled out below.
2. **Get Kantata credentials from your admin** — Usually **OAuth client ID + client secret** (for `kantata login`), an **org-hosted login URL** plus **`kantata import-credentials`** (no secret on your machine), or a **bearer access token** only. If you are not sure what to ask for, read **section 1** above.
3. **Add the MCP server to your client** — In Cursor (or similar), add a `kantata` entry with **`uvx`**, **`--from`**, **`git+https://github.com/kleinjoshuaa/kantata-mcp.git`**, and **`kantata-mcp`** (full example under **MCP server in Cursor** below). You can **omit the whole `env` block** if you will use the default token file after login.
4. **Sign in once from a terminal** — **OAuth (local):** set **`KANTATA_CLIENT_ID`** and **`KANTATA_CLIENT_SECRET`**, then run **`kantata login`**. **OAuth (org script):** open your org’s Apps Script URL, then pipe or paste the JSON into **`kantata import-credentials`** (see **Import credentials from JSON** below). **Bearer only:** set **`KANTATA_ACCESS_TOKEN`** and skip login. (Prefix with **`uvx --from …`** if you use Option A.)
5. **Restart or refresh MCP in the IDE** — So the server reloads your saved token or updated `env`. If auth fails, check that MCP `env` does not set a stale **`KANTATA_ACCESS_TOKEN`** that overrides your credentials file.

### Prerequisites

- **[uv](https://docs.astral.sh/uv/)** — enough for the recommended **uvx** workflow below (uv can fetch a compatible Python for the tool).
- From your Kantata admin: either an **OAuth client ID and secret**, or a **bearer access token** you are allowed to use with the API

### Option A — Run with `uvx` (no clone, no venv)

You do **not** need to clone this repository or create a virtualenv. [uvx](https://docs.astral.sh/uv/guides/tools/) installs the published package into a cache, runs the command, and leaves your token on disk like any other install.

**Stable URL for this project** (replace if you use a fork):

`git+https://github.com/kleinjoshuaa/kantata-mcp.git`

Pin a tag or branch if you want a fixed revision, for example  
`git+https://github.com/kleinjoshuaa/kantata-mcp.git@v0.1.0` (after you tag releases).

#### OAuth login with `uvx` — yes, it works

`kantata login` is the same flow whether you run **`kantata`** via **`uvx`** from git or from a local venv install: you set **`KANTATA_CLIENT_ID`** and **`KANTATA_CLIENT_SECRET`**, run login, approve in the browser, and the tool writes **`~/.config/kantata/credentials.json`** (or **`KANTATA_CREDENTIALS_PATH`**). The ephemeral environment `uvx` uses only affects *where the code runs from*; it does not change OAuth or file paths.

```bash
export KANTATA_CLIENT_ID="…your client id…"
export KANTATA_CLIENT_SECRET="…your client secret…"
uvx --from git+https://github.com/kleinjoshuaa/kantata-mcp.git kantata login
```

Other CLI commands:

```bash
uvx --from git+https://github.com/kleinjoshuaa/kantata-mcp.git kantata whoami
uvx --from git+https://github.com/kleinjoshuaa/kantata-mcp.git kantata list-projects --search "demo"
```

Shorter shell life: define a tiny alias or script that prepends `uvx --from git+https://github.com/kleinjoshuaa/kantata-mcp.git` before `kantata …`.

#### Import credentials from JSON (`uvx` one-liners)

If your admin gave you token JSON (for example from a **Google Apps Script** page after Kantata consent), write the default credentials file without hand-editing paths:

```bash
# macOS: JSON is on the clipboard after copying from the browser
pbpaste | uvx --from git+https://github.com/kleinjoshuaa/kantata-mcp.git kantata import-credentials
```

```bash
# From a saved file
uvx --from git+https://github.com/kleinjoshuaa/kantata-mcp.git kantata import-credentials --file ~/Downloads/kantata-token.json
```

The JSON must include a string **`access_token`** (and may include **`token_type`**; default is `bearer`). Set **`KANTATA_CREDENTIALS_PATH`** first if you want a non-default file path.

### Option B — Clone and install into a venv

For a local checkout or development:

```bash
cd kantata-mcp    # your clone directory
uv venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
uv pip install -e .
```

With dev dependencies (tests, Ruff):

```bash
uv pip install -e ".[dev]"
```

You then run **`kantata`** and **`kantata-mcp`** from that environment.

| Command | Role |
|---------|------|
| `kantata` | CLI |
| `kantata-mcp` | MCP server (stdio) for Cursor, Claude Code, etc. |

### Sign in with OAuth (recommended)

1. Obtain **client ID** and **client secret** from your Kantata administrator (see section 1).
2. In a terminal, set:

   ```bash
   export KANTATA_CLIENT_ID="…your client id…"
   export KANTATA_CLIENT_SECRET="…your client secret…"
   ```

3. Run **`kantata login`** — either the bare command (option B) or via **`uvx … kantata login`** (option A).

   A browser window opens (unless you pass **`--no-browser`** and open the printed URL yourself). After you approve access, the tool writes **`~/.config/kantata/credentials.json`** (mode `0600` on Unix) containing an access token.

**Port in use:** run `kantata login --port 8899` (example) and ensure that redirect URI is registered in Kantata, or set **`KANTATA_OAUTH_CALLBACK_PORT`** to match what is registered.

**Custom credentials file:** set **`KANTATA_CREDENTIALS_PATH`** to an absolute path before login and when running MCP so every component reads the same file.

### Import credentials from JSON

Use this when an **org-hosted** flow (for example **Google Apps Script**) returns Kantata token JSON and you do not have **`KANTATA_CLIENT_ID`** / **`KANTATA_CLIENT_SECRET`** on your machine.

1. Obtain JSON containing at least **`access_token`** (same shape as after `kantata login`).
2. Run **`kantata import-credentials`** with that JSON on **stdin**, or pass **`--file /path/to/token.json`**.
3. The tool writes **`~/.config/kantata/credentials.json`** (or **`KANTATA_CREDENTIALS_PATH`**) with mode **`0600`** on Unix.

Examples (option B after `uv pip install`; use the **`uvx`** lines from option A if you do not have a venv):

```bash
pbpaste | kantata import-credentials
```

```bash
kantata import-credentials --file ./kantata-token.json
```

Interactive terminal with no pipe: use **`--file`** or a heredoc, for example **`kantata import-credentials <<'EOF'`** … **`EOF`**.

### Sign in with a bearer token only

If your organization gave you a token instead of OAuth credentials:

```bash
export KANTATA_ACCESS_TOKEN="…token…"
```

Optional non-default API host:

```bash
export KANTATA_API_BASE="https://…/api/v1"
```

If **`KANTATA_ACCESS_TOKEN`** is set to a non-empty value, it **overrides** the credentials file. Leave it unset (or empty) to use the file from `kantata login`.

### Quick CLI check

```bash
kantata whoami
kantata list-projects --search "demo"
```

With **uvx**, prefix the same commands as in option A, for example  
`uvx --from git+https://github.com/kleinjoshuaa/kantata-mcp.git kantata whoami`.

Use `kantata --help` and `kantata <command> --help` for the full command list (tasks, time, posts, join/leave project, etc.).

### MCP tools (`kantata-mcp`)

The stdio MCP server exposes the tools below (names are stable for clients such as Cursor). Each runs as the authenticated Kantata user unless noted.

| Tool | What it does |
|------|----------------|
| `kantata_whoami` | Return the current user (id, name, email, etc.). |
| `kantata_list_users` | List or search users (by workspace, name search, exact email, or account-wide). |
| `kantata_list_projects` | List workspaces you participate in; optional text search. |
| `kantata_list_joinable_projects` | List projects you can join but are not on yet. |
| `kantata_join_project` | Add yourself to a workspace (default role: maven). |
| `kantata_leave_project` | Remove your participation from a workspace. |
| `kantata_list_tasks` | List stories/tasks for a project; optional parent filter, search, and WBS labels. |
| `kantata_get_story` | Fetch one task/story by id. |
| `kantata_create_task` | Create a task (or milestone/issue); optional parent, description, assign self. |
| `kantata_update_task` | Update title, description, parent, type, or replace assignees with yourself. |
| `kantata_adjust_task_assignees` | Add or remove assignees without replacing everyone (or full replace). |
| `kantata_delete_task` | Soft-delete a task/story. |
| `kantata_log_time` | Create a project time entry (date, minutes, optional task and notes). |
| `kantata_list_time_entries` | List time entries with optional workspace, date range, user, and includes. |
| `kantata_update_time_entry` | Change notes, date, duration, task link, or billable flag on a time entry. |
| `kantata_delete_time_entry` | Delete one time entry by id. |
| `kantata_log_time_off` | Create account time off for one or more dates (hours per day; optional user id). |
| `kantata_list_time_off_entries` | List time off entries (date range, user, workspace, etc.). |
| `kantata_submit_timesheet` | Submit a timesheet for a workspace and date range. |
| `kantata_post_project_update` | Post to project activity; optional attachments, private recipients, linked task. |
| `kantata_update_post` | Edit an existing activity post (message and/or link to a task). |
| `kantata_link_post_to_task` | Link an existing post to a task without changing the message. |

### MCP server in Cursor (or similar)

The MCP process uses the **same auth rules** as the CLI:

1. If **`KANTATA_ACCESS_TOKEN`** is set and non-whitespace, that token is used.
2. Otherwise the tool reads **`access_token`** from a JSON credentials file. The file path is **`KANTATA_CREDENTIALS_PATH`** if set, or by default **`~/.config/kantata/credentials.json`** (i.e. `$HOME/.config/kantata/credentials.json`).

So if you ran **`kantata login`** with defaults and do not set **`KANTATA_ACCESS_TOKEN`** in MCP `env`, you do **not** need **`KANTATA_CREDENTIALS_PATH`** in `mcp.json` at all—the default path is used automatically.

**Using `uvx` (no path to a venv binary):** `uv` must be on your **`PATH`** when the IDE starts the server.

To keep **OAuth client id and secret out of `mcp.json`**, run **`kantata login`** in a terminal first (export `KANTATA_CLIENT_ID` / `KANTATA_CLIENT_SECRET` there only for that session), or run **`kantata import-credentials`** after getting JSON from an org-hosted script. The MCP server uses the saved **access token** file, not the OAuth pair.

**Minimal config** (default token file after `kantata login`):

```json
{
  "mcpServers": {
    "kantata": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/kleinjoshuaa/kantata-mcp.git", "kantata-mcp"]
    }
  }
}
```

**Only if** the token lives somewhere else (or `HOME` for the IDE process differs from the account where you logged in), set **`KANTATA_CREDENTIALS_PATH`** to an **absolute** path in `env`.

**Using a local venv** (option B): point `command` at the absolute path to `kantata-mcp` inside `.venv`, still with no `env` when defaults work.

Add **`KANTATA_API_BASE`** in `env` only if your admin said so.

**Important:** The IDE does **not** load your shell profile for MCP. Only variables you put in MCP config (plus the process environment) apply.

**After `kantata login`:** restart the MCP server in the IDE so it reloads the token file.

**401 / auth errors:** token invalid or revoked, or wrong account; run **`kantata login`** or **`kantata import-credentials`** again, or update **`KANTATA_ACCESS_TOKEN`**. If MCP sets **`KANTATA_ACCESS_TOKEN`** to a stale value, it overrides the file—remove or update it.

**Optional (macOS):** to avoid putting a token in JSON, you can wrap the server with [`scripts/run_kantata_mcp_keychain.sh`](scripts/run_kantata_mcp_keychain.sh) and store the token in Keychain; see comments in that script.

### Environment variables (reference)

| Variable | Purpose |
|----------|---------|
| `KANTATA_ACCESS_TOKEN` | Bearer token; if set and non-whitespace, overrides the credentials file |
| `KANTATA_CLIENT_ID` / `KANTATA_CLIENT_SECRET` | Required for `kantata login` |
| `KANTATA_CREDENTIALS_PATH` | JSON file with `access_token` (default: `~/.config/kantata/credentials.json`) |
| `KANTATA_API_BASE` | API root (default `https://api.mavenlink.com/api/v1`) |
| `KANTATA_OAUTH_AUTHORIZE` / `KANTATA_OAUTH_TOKEN` | Override OAuth endpoints (rare) |
| `KANTATA_OAUTH_CALLBACK_PORT` | Local callback port when not using `--port` on login (default **8765**) |

### Development (optional)

```bash
uv sync --extra dev
uv run ruff check src tests
uv run pytest -q
```

CI: [.github/workflows/ci.yml](.github/workflows/ci.yml).

### Limitations (short)

Joinable workspaces are inferred from API visibility; timesheet windows must match your org’s rules; MCP attachment paths must be **absolute** and readable by the server process; fine-grained OAuth scopes are not modeled—access follows the signed-in Kantata user.

---

Kantata OX and Mavenlink are trademarks of their respective owners. This is an independent open-source client.
