# adversarial-review: diff target caps context before redaction, so a secret cut at the cap can leak a prefix

Found in the plan 59 quality review. _build_target caps the diff text (run_review.py ~810/823) before build_target redacts it (~787). A token straddling the cap no longer matches the redaction regex, so its prefix reaches the prompt. Applies to the council and to --prompt-only. Fix: redact first, then cap; add a cap-boundary test.
