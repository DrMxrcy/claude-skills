# Typed human-readable ID prefixes (TSK-42, BUG-7) as display layer over int ids

From todowrite research (dderyldowney/todowrite): every layer has a typed ID prefix (GOAL-*, TSK-*) over integer PKs. For roadmap: keep int ids as the source of truth; render type-prefixed ids (FEAT-12, BUG-7, REF-3, CHORE-9) in CLI output, status, next, orient, and suggested commit messages. Accept both forms as input (--plan 7 or --plan BUG-7). Display-only change, no schema migration.
