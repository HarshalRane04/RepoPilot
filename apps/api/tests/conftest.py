from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT / "packages" / "shared_contracts"))
sys.path.insert(0, str(ROOT / "packages" / "evals"))
sys.path.insert(0, str(ROOT / "packages" / "policy_engine"))
sys.path.insert(0, str(ROOT / "packages" / "llm_client"))
sys.path.insert(0, str(ROOT / "packages" / "github_client"))
