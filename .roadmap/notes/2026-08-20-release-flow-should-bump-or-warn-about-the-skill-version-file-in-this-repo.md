# Release flow should bump or warn about the skill VERSION file in this repo

Version review found skills/roadmap/VERSION at 0.14.2 while cutting 0.16.0 — release() never touches it and orient/handoff self-report stale versions. Repo-specific: add a release checklist step, hook, or test asserting VERSION matches the version being cut in claude-skills.
