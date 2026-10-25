# Optional execution metadata on check — record verify command and result per step

From todowrite research: its Command layer stores cmd, params, output, artifacts per executed task. Lightweight roadmap version: 'check --plan N --step M --verify "pytest -q" --result "193 passed"' (or auto-capture) appends an audit line per checked step (in plan file or .roadmap/ log). Gives catchup/review a trail of what was actually run to justify each check-off. Keep optional — zero friction when omitted.
