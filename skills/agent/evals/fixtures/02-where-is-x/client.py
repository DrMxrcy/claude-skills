"""HTTP-ish client (network stubbed for the fixture)."""
import config


def fetch(url):
    return {"url": url, "timeout": config.get("timeout")}
