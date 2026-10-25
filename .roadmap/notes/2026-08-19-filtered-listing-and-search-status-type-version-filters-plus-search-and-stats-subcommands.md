# Filtered listing and search: status --type/--version filters, plus search and stats subcommands

From todowrite research: its CLI has list/search/stats with --layer/--owner/--status filters. Roadmap's status shows everything; no way to filter by type or text-search titles/notes/plans. Add: 'status --type bug', 'status --version X', 'search <text>' (titles, notes, plan bodies, incubator), maybe 'stats' (counts by type/status/version). Small argparse + filter additions, JSON output included.
