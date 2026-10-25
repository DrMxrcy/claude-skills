"""Settings with environment overrides."""
import os

DEFAULTS = {"timeout": 30, "retries": 2}


def get(key):
    env = os.environ.get("APP_" + key.upper())
    if env is not None:
        return type(DEFAULTS[key])(env)
    return DEFAULTS[key]
