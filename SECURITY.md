# Security

## Reporting issues

If you believe you have found a security vulnerability in **this repository** (the `kantata-assist` CLI/MCP client code), please open a **private** security advisory on GitHub (or contact the maintainers through the channel listed on the repository) with enough detail to reproduce the issue.

This project is a **thin API client** for [Kantata OX](https://developer.kantata.com/). Vulnerabilities in Kantata’s servers, OAuth implementation, or account configuration should be reported to **Kantata** through their appropriate channels, not only through this repo.

## Secrets

Never commit OAuth **client secrets**, **access tokens**, or **refresh tokens**. Use environment variables or a credentials file with restrictive permissions (`0600`). See the [README](README.md#authentication) for supported patterns.
