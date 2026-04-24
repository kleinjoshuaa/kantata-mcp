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

- **Python 3.11+**
- **[uv](https://docs.astral.sh/uv/)** recommended (or any PEP 517 installer)
- From your Kantata admin: either an **OAuth client ID and secret**, or a **bearer access token** you are allowed to use with the API

### Install

From a clone of this repository:

```bash
cd kantata-assist    # your clone directory
uv venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
uv pip install -e .
```

With dev dependencies (tests, Ruff):

```bash
uv pip install -e ".[dev]"
```

After install you have two commands:

| Command | Role |
|---------|------|
| `kantata` | CLI |
| `kantata-mcp` | MCP server (stdio) for Cursor, Claude Code, etc. |

### Sign in with OAuth (recommended)

1. Obtain **client ID** and **client secret** from your Kantata administrator (see section 1).
2. In a terminal (same environment where `kantata` is installed), set:

   ```bash
   export KANTATA_CLIENT_ID="…your client id…"
   export KANTATA_CLIENT_SECRET="…your client secret…"
   ```

3. Run:

   ```bash
   kantata login
   ```

   A browser window opens (unless you pass **`--no-browser`** and open the printed URL yourself). After you approve access, the tool writes **`~/.config/kantata/credentials.json`** (mode `0600` on Unix) containing an access token.

**Port in use:** run `kantata login --port 8899` (example) and ensure that redirect URI is registered in Kantata, or set **`KANTATA_OAUTH_CALLBACK_PORT`** to match what is registered.

**Custom credentials file:** set **`KANTATA_CREDENTIALS_PATH`** to an absolute path before login and when running MCP so every component reads the same file.

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

Use `kantata --help` and `kantata <command> --help` for the full command list (tasks, time, posts, join/leave project, etc.).

### MCP server in Cursor (or similar)

The MCP process uses the **same auth rules** as the CLI: non-empty **`KANTATA_ACCESS_TOKEN`**, else JSON at **`KANTATA_CREDENTIALS_PATH`**, else **`~/.config/kantata/credentials.json`**.

Example **user-level** MCP config (paths must be **absolute** on your machine):

```json
{
  "mcpServers": {
    "kantata": {
      "command": "/Users/you/code/kantata-assist/.venv/bin/kantata-mcp",
      "env": {
        "KANTATA_CREDENTIALS_PATH": "/Users/you/.config/kantata/credentials.json"
      }
    }
  }
}
```

Omit `env` if the default credentials path is fine. Add **`KANTATA_API_BASE`** only if your admin said so.

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
