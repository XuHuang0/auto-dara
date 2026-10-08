import os
from pathlib import Path

from dotenv import load_dotenv

for _env in (Path.cwd() / ".env", Path(__file__).resolve().parent.parent / ".env"):
    if _env.exists():
        load_dotenv(_env, override=False)

# keep Ray from flooding the terminal with internal log messages
for _k, _v in {
    "RAY_BACKEND_LOG_LEVEL": "fatal",
    "RAY_ACCEL_ENV_VAR_OVERRIDE_ON_ZERO": "0",
    "RAY_USAGE_STATS_ENABLED": "0",
    "RAY_DEDUP_LOGS": "0",
    "RAY_ADDRESS": "local",
}.items():
    os.environ.setdefault(_k, _v)
