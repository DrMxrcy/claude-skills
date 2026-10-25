"""Claim owners and the work-in-progress limit (plan 40).

An item's claim may name an owner (`claim_owner`) and the moment that owner
last refreshed it (`claim_refreshed`, UTC ISO timestamp). A claim with an owner
refreshed within `settings.claimTtlHours` (default 12) is *held*: another owner
cannot change or clear it without `--take`, and `next` skips it. A claim with
no owner (written before plan 40, or with no identity available) is never held.

`settings.wipLimit` (default none) caps in-flight items; going over it only
warns — nothing is refused.

Layer: rmcore only (stdlib + config), so parse/sync/ops/report can all use it.
"""
from __future__ import annotations
import datetime
import os
import subprocess
from pathlib import Path

DEFAULT_CLAIM_TTL_HOURS = 12.0
OWNER_ENV = "ROADMAP_OWNER"
# Agent CLIs that announce themselves through the environment; the last
# fallback when neither ROADMAP_OWNER nor a git user name is available.
AGENT_ENV = (("CLAUDECODE", "claude"), ("GEMINI_CLI", "gemini"))


def now() -> datetime.datetime:
    """Current UTC time (one seam for tests)."""
    return datetime.datetime.now(datetime.timezone.utc)


def stamp(when: datetime.datetime | None = None) -> str:
    """`2026-10-23T14:05:09Z` — the claim_refreshed format."""
    return (when or now()).astimezone(datetime.timezone.utc) \
        .replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def clean_owner(name: str | None) -> str | None:
    """One-line owner name, or None when empty."""
    if name is None:
        return None
    return " ".join(str(name).split()) or None


def default_owner(root: Path) -> str | None:
    """$ROADMAP_OWNER, else `git config user.name`, else the agent name when the
    environment names one, else None."""
    env = clean_owner(os.environ.get(OWNER_ENV))
    if env:
        return env
    try:
        out = subprocess.run(["git", "config", "user.name"], cwd=str(root),
                             capture_output=True, text=True)
        name = clean_owner(out.stdout) if out.returncode == 0 else None
    except (FileNotFoundError, OSError):
        name = None
    if name:
        return name
    for var, agent in AGENT_ENV:
        if os.environ.get(var):
            return agent
    return None


def _number(settings: dict, key: str) -> float | None:
    """settings[key] as a positive number, else None (absent, junk, or <= 0)."""
    raw = settings.get(key)
    if isinstance(raw, bool):
        return None
    try:
        n = float(raw)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def claim_ttl_hours(cfg: dict) -> float:
    """settings.claimTtlHours, default 12. 0 or negative disables holds."""
    settings = cfg.get("settings") or {}
    if "claimTtlHours" in settings and not isinstance(settings["claimTtlHours"], bool):
        try:
            return max(0.0, float(settings["claimTtlHours"]))
        except (TypeError, ValueError):
            pass
    return DEFAULT_CLAIM_TTL_HOURS


def wip_limit(cfg: dict) -> int | None:
    """settings.wipLimit as a positive int, or None (no limit)."""
    n = _number(cfg.get("settings") or {}, "wipLimit")
    return int(n) if n else None


def refreshed_at(claim: dict | None) -> datetime.datetime | None:
    """When the claim was last refreshed: claim_refreshed, else the start of its
    `updated` date (a hand-written owner with no timestamp). None when unknown."""
    claim = claim or {}
    for raw in (claim.get("refreshed"), claim.get("updated")):
        if not raw:
            continue
        try:
            when = datetime.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            continue
        return when if when.tzinfo else when.replace(tzinfo=datetime.timezone.utc)
    return None


def holder(claim: dict | None, ttl_hours: float,
           at: datetime.datetime | None = None) -> str | None:
    """The owner holding this claim right now, or None when it is not held (no
    claim, no owner, never refreshed, older than the TTL, or TTL 0)."""
    owner = clean_owner((claim or {}).get("owner"))
    if not owner or ttl_hours <= 0:
        return None
    when = refreshed_at(claim)
    if when is None:
        return None
    age = (at or now()) - when
    return owner if age <= datetime.timedelta(hours=ttl_hours) else None


def same_owner(a: str | None, b: str | None) -> bool:
    return bool(a and b) and a.casefold() == b.casefold()


def held_by_other(claim: dict | None, owner: str | None, ttl_hours: float,
                  at: datetime.datetime | None = None) -> str | None:
    """The other owner holding `claim`, or None when it is free or `owner`'s own.
    An unknown `owner` (None) never matches a holder."""
    h = holder(claim, ttl_hours, at)
    return None if h is None or same_owner(h, owner) else h


def age(claim: dict | None, at: datetime.datetime | None = None) -> str:
    """`5m` / `3h` / `2d` since the claim was refreshed; empty when unknown."""
    when = refreshed_at(claim)
    if when is None:
        return ""
    secs = max(0, int(((at or now()) - when).total_seconds()))
    for unit, size in (("w", 604800), ("d", 86400), ("h", 3600), ("m", 60)):
        if secs >= size:
            return f"{secs // size}{unit}"
    return "now"


def held_message(plan_id: int, by: str, claim: dict | None) -> str:
    a = age(claim)
    return (f"#{plan_id} is held by {by}" + (f" (claimed {a} ago)" if a and a != "now"
                                            else " (claimed just now)")
            + f" — pass --take to take it over")


def wip(in_flight: int, cfg: dict) -> dict | None:
    """{"count", "limit", "over"} when settings.wipLimit is set, else None."""
    limit = wip_limit(cfg)
    if limit is None:
        return None
    return {"count": in_flight, "limit": limit, "over": in_flight > limit}


def wip_warning(payload: dict | None) -> str | None:
    """The one warning line printed by orient / next / status, or None."""
    if not payload or not payload.get("over"):
        return None
    n, limit = payload["count"], payload["limit"]
    return (f"work in progress: {n} in-flight items, over settings.wipLimit "
            f"({limit}) — finish or land one before starting another")
