"""Background worker."""
import config

idle_timeout = 5  # seconds the worker sleeps between polls; NOT the request timeout


def run_once(job):
    deadline = config.get("timeout") * config.get("retries")
    return {"job": job, "deadline": deadline, "sleep": idle_timeout}
