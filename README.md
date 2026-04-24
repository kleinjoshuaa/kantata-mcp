# Kantata Assist

Kantata Assist is a small Python toolkit for [Kantata OX](https://developer.kantata.com/kantata/specification) (formerly Mavenlink): a **CLI** (`kantata`) and a **stdio MCP server** (`kantata-mcp`) so people can work with projects, tasks, time, and activity from the terminal or from AI tools such as Cursor.

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

### Governance checklist

- **Roles:** Confirm who may create OAuth apps and use the API (often account administrators). See Kantata’s [API overview](https://knowledge.kantata.com/hc/en-us/articles/202811760-Kantata-API-Overview).
- **Secrets:** Do not put client secrets or bearer tokens in source control, screenshots, or broad chat logs. Prefer a password manager or internal secret store for distributing the OAuth pair to trusted users.
- **Rate limits:** Kantata applies [API rate limits](https://knowledge.kantata.com/hc/en-us/articles/9698066628123); heavy automation should be paced and monitored.
- **Support:** Decide whether users file tickets with **you** (internal IT) or with the maintainers of this open-source repo for tool bugs.

### What to give each user

At minimum, users who will use **OAuth** need:

- **Client ID** and **client secret** for the app you registered (unless you use a different org-wide pattern they already have).
- The **redirect URI** (and port) they must register or that you pre-registered.
- Optional: non-default **API base** if your tenant uses a different host than the tool default (`https://api.mavenlink.com/api/v1`), via **`KANTATA_API_BASE`**.

Users who will use only a **bearer token** need the token (and rotation procedure), not the OAuth pair.

---

## 2. For users installing Kantata Assist

This section is for **you** if you want the CLI and/or MCP server on your computer.

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

### OAuth client ID and secret via LastPass CLI (`lpass`)

If you use [LastPass](https://www.lastpass.com/) and the [lastpass-cli](https://github.com/lastpass/lastpass-cli) (`brew install lastpass-cli` on macOS), you can load the Kantata OAuth **client ID** and **client secret** from a vault item at runtime instead of pasting them into the terminal or into `mcp.json`.

1. **Sign in to the CLI** (when your session expires):

   ```bash
   lpass login
   ```

2. **Store the pair in LastPass** in a way `lpass` can read:

   - **Secure Note** (recommended): add custom fields named exactly what you will pass to `--field`, e.g. `Client ID` and `Client Secret`.
   - **Or** a generic “password” site entry: put the client id in **Username** and the client secret in **Password** (then use `--username` / `--password` below instead of `--field`).

   Use the item’s full path as shown in LastPass (folders allowed), e.g. `Shared-Engineering/Kantata OAuth`.

3. **Login from the shell** without pasting secrets (adjust `ITEM` and field names to match your vault):

   ```bash
   ITEM="Shared-Engineering/Kantata OAuth"
   export KANTATA_CLIENT_ID="$(lpass show "$ITEM" --field='Client ID' | tr -d '\r\n')"
   export KANTATA_CLIENT_SECRET="$(lpass show "$ITEM" --field='Client Secret' | tr -d '\r\n')"
   uvx --from git+https://github.com/kleinjoshuaa/kantata-mcp.git kantata login
   ```

   If you used **Username** / **Password** on the item:

   ```bash
   export KANTATA_CLIENT_ID="$(lpass show "$ITEM" --username | tr -d '\r\n')"
   export KANTATA_CLIENT_SECRET="$(lpass show "$ITEM" --password | tr -d '\r\n')"
   ```

   `tr -d '\r\n'` avoids stray newlines some `lpass` versions print.

4. **`mcp.json` without OAuth secrets** — After a successful `kantata login`, **`kantata-mcp` only needs your Kantata access token** from the default credentials file (**`~/.config/kantata/credentials.json`**) unless you override the path with **`KANTATA_CREDENTIALS_PATH`**. It does **not** read `KANTATA_CLIENT_ID` / `KANTATA_CLIENT_SECRET`. So your MCP config should **not** include the OAuth client or secret in `env`. You usually **omit the whole `env` block** (see [MCP server](#mcp-server-in-cursor-or-similar)); add **`KANTATA_CREDENTIALS_PATH`** or **`KANTATA_API_BASE`** only when you need a non-default location or API host.

   If you still want a **launcher script** as `command` (for example to avoid repeating `uvx` args or to force a known `PATH`), the script can be minimal — no LastPass calls required for normal MCP operation:

   ```bash
   # ~/bin/kantata-mcp-uvx.sh  (example — chmod +x)
   exec uvx --from git+https://github.com/kleinjoshuaa/kantata-mcp.git kantata-mcp
   ```

   Cursor (or another client) would use `"command": "/Users/you/bin/kantata-mcp-uvx.sh"` with **no `env`** if the default token file is fine.

5. **Optional: one script for “login with LastPass”** so you never type the `export` lines:

   Save as e.g. `~/bin/kantata-login-lpass.sh`, `chmod +x`, edit `ITEM` / field names once:

   ```bash
   #!/usr/bin/env sh
   set -e
   ITEM="${KANTATA_LPASS_ITEM:-Shared-Engineering/Kantata OAuth}"
   export KANTATA_CLIENT_ID="$(lpass show "$ITEM" --field='Client ID' | tr -d '\r\n')"
   export KANTATA_CLIENT_SECRET="$(lpass show "$ITEM" --field='Client Secret' | tr -d '\r\n')"
   UV_FROM="${KANTATA_UV_FROM:-git+https://github.com/kleinjoshuaa/kantata-mcp.git}"
   exec uvx --from "$UV_FROM" kantata login "$@"
   ```

   Then run: `kantata-login-lpass.sh` (or pass `--port 8899` etc. as extra args).

**Operational notes:** `lpass` must be able to read the item (same LastPass account, correct folder name). For automation, your org’s LastPass policy may require device approval or MFA — that is outside this tool. Do not commit scripts that embed item names if they reveal sensitive structure; using **`KANTATA_LPASS_ITEM`** in the environment keeps the script generic.

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

### MCP server in Cursor (or similar)

The MCP process uses the **same auth rules** as the CLI:

1. If **`KANTATA_ACCESS_TOKEN`** is set and non-whitespace, that token is used.
2. Otherwise the tool reads **`access_token`** from a JSON credentials file. The file path is **`KANTATA_CREDENTIALS_PATH`** if set, or by default **`~/.config/kantata/credentials.json`** (i.e. `$HOME/.config/kantata/credentials.json`).

So if you ran **`kantata login`** with defaults and do not set **`KANTATA_ACCESS_TOKEN`** in MCP `env`, you do **not** need **`KANTATA_CREDENTIALS_PATH`** in `mcp.json` at all—the default path is used automatically.

**Using `uvx` (no path to a venv binary):** `uv` must be on your **`PATH`** when the IDE starts the server.

To keep **OAuth client id and secret out of `mcp.json`**, rely on a prior `kantata login` (see [LastPass CLI](#oauth-client-id-and-secret-via-lastpass-cli-lpass) if you load those credentials only at login time). The MCP server uses the saved **access token** file, not the OAuth pair.

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

**401 / auth errors:** token expired or wrong; run `kantata login` again or refresh the bearer token. If MCP sets `KANTATA_ACCESS_TOKEN` to a stale value, it overrides the file—remove or update it.

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
