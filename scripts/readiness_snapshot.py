from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SENSITIVE_KEY_PARTS = ("secret", "token", "private_key", "api_key", "password")
SENSITIVE_OUTPUT_PATTERNS = (
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL),
)


@dataclass(frozen=True)
class ReadinessSnapshot:
    generated_at: str
    readiness: dict[str, Any]
    github_app: dict[str, Any] | None

    def as_dict(self) -> dict[str, Any]:
        return {"generated_at": self.generated_at, "readiness": self.readiness, "github_app": self.github_app}


def redact(value: Any, *, key: str = "") -> Any:
    lowered = key.lower()
    if any(part in lowered for part in SENSITIVE_KEY_PARTS) and not isinstance(value, bool):
        if value in (None, "", False):
            return value
        return "[redacted]"
    if isinstance(value, dict):
        return {item_key: redact(item_value, key=item_key) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def curl_json(url: str) -> dict[str, Any]:
    curl_path = shutil.which("curl")
    if curl_path is None:
        raise RuntimeError("curl is required to capture readiness snapshots.")
    result = subprocess.run([curl_path, "-sS", "--max-time", "15", url], capture_output=True, check=False, text=True)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip() or f"curl exited with {result.returncode}")
    payload = json.loads(result.stdout)
    if not isinstance(payload, dict):
        raise RuntimeError(f"{url} did not return a JSON object.")
    return payload


def capture_snapshot(*, readiness_url: str, github_app_url: str | None) -> ReadinessSnapshot:
    readiness = redact(curl_json(readiness_url))
    github_app = redact(curl_json(github_app_url)) if github_app_url else None
    return ReadinessSnapshot(generated_at=datetime.now(timezone.utc).isoformat(), readiness=readiness, github_app=github_app)


def render_markdown(snapshot: ReadinessSnapshot) -> str:
    readiness = snapshot.readiness
    lines = [
        "# RepoPilot Credential Readiness Snapshot",
        "",
        f"- Generated at: `{snapshot.generated_at}`",
        f"- Environment: `{readiness.get('environment', 'unknown')}`",
        f"- Production ready: `{readiness.get('production_ready')}`",
        f"- GitHub mode: `{readiness.get('github_mode', 'unknown')}`",
        f"- Model mode: `{readiness.get('model_mode', 'unknown')}`",
        f"- GitHub writes enabled: `{readiness.get('github_writes_enabled')}`",
        "",
        "## Integrations",
        "",
        "| Integration | State | Mode | Required | Detail | Next Step |",
        "|---|---|---|---|---|---|",
    ]
    for integration in readiness.get("integrations", []):
        if not isinstance(integration, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    str(integration.get("name", "")),
                    str(integration.get("state", "")),
                    str(integration.get("mode", "")),
                    str(integration.get("required_for_production", "")),
                    str(integration.get("detail", "")).replace("|", "/"),
                    str(integration.get("next_step", "")).replace("|", "/"),
                ]
            )
            + " |"
        )
    blockers = readiness.get("blockers", [])
    warnings = readiness.get("warnings", [])
    lines.extend(["", "## Blockers", ""])
    lines.extend([f"- {item}" for item in blockers] or ["- None"])
    lines.extend(["", "## Warnings", ""])
    lines.extend([f"- {item}" for item in warnings] or ["- None"])
    if snapshot.github_app is not None:
        lines.extend(["", "## GitHub App Field Status", "", "| Field | Configured | Secret | Source |", "|---|---|---|---|"])
        for field in snapshot.github_app.get("fields", []):
            if not isinstance(field, dict):
                continue
            lines.append(
                f"| {field.get('name', '')} | {field.get('configured', '')} | {field.get('secret', '')} | {field.get('source', '')} |"
            )
    lines.append("")
    return "\n".join(lines)


def redact_rendered_markdown(value: str) -> str:
    redacted = value
    for pattern in SENSITIVE_OUTPUT_PATTERNS:
        redacted = pattern.sub("[redacted]", redacted)
    return redacted


def write_outputs(*, snapshot: ReadinessSnapshot, json_out: Path | None, md_out: Path | None) -> None:
    if json_out:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(json.dumps(snapshot.as_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if md_out:
        md_out.parent.mkdir(parents=True, exist_ok=True)
        md_out.write_text(render_markdown(snapshot), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Capture redacted RepoPilot readiness evidence from the running local API.")
    parser.add_argument("--readiness-url", default="http://127.0.0.1:8000/settings/readiness")
    parser.add_argument("--github-app-url", default="http://127.0.0.1:8000/settings/github/app")
    parser.add_argument("--json-out", type=Path, default=Path("Docs/release-artifacts/credential-readiness-snapshot.json"))
    parser.add_argument("--md-out", type=Path, default=Path("Docs/release-artifacts/credential-readiness-snapshot.md"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    snapshot = capture_snapshot(readiness_url=args.readiness_url, github_app_url=args.github_app_url)
    write_outputs(snapshot=snapshot, json_out=args.json_out, md_out=args.md_out)
    print("Credential readiness snapshot completed; redacted artifacts were written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
