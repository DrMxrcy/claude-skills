# Vendored security checklists (secaudit)

These files are copies of `skills/<domain>/SKILL.md` from **secaudit** v3.13.0 (commit `537bbbfd00e4`), https://github.com/DrMxrcy/secaudit, renamed `<domain>.md`. Two changes are made at sync time. A one-line header after the frontmatter maps `secaudit:<domain>` to the sibling `<domain>.md`. Relative links to upstream `references/*.md` files, which are not vendored, are rewritten to say "(not vendored)". Everything else is verbatim.

License: MIT. Copyright (c) 2025 Chris Raroque. The full license text is in `LICENSE` next to this file and applies to every `<domain>.md` here.

Do not edit these files. Re-sync with `python3 skills/adversarial-review/scripts/sync-security-refs.py` after `claude plugin update secaudit@secaudit`. `--check` reports staleness. The adversarial review never requires the plugin to be installed.

Domains: `ai-integration`, `api-surface`, `audit`, `auth`, `better-auth-security`, `ci-cd-security`, `cloudflare-workers-security`, `convex-security`, `cryptography`, `data-access`, `database`, `deployment`, `discord-bot-security`, `docker-security`, `dynamic-verification`, `expo-security`, `fivem-security`, `framework-versions`, `kubernetes-security`, `logging-monitoring`, `mcp-agent-security`, `multi-tenant-isolation`, `oauth-oidc-security`, `object-storage-security`, `payments`, `postgres-security`, `prisma-security`, `privilege-escalation`, `proxy-trust`, `python-web-security`, `rate-limiting`, `react-native-security`, `realtime-security`, `revenuecat-security`, `rich-text-security`, `secrets`, `supply-chain`, `web-vulns`, `webhook-security`
