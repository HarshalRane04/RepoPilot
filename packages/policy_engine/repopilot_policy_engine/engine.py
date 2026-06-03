from __future__ import annotations

import fnmatch
import shlex
from dataclasses import dataclass, field

from repopilot_contracts import ImplementationPlan, PolicyDecision, PolicyDecisionType


@dataclass(frozen=True)
class PolicyConfig:
    max_files_changed_without_approval: int = 5
    max_commands_without_approval: int = 6
    high_risk_patterns: tuple[str, ...] = (
        ".github/workflows/**",
        "**/auth/**",
        "**/payments/**",
        "**/migrations/**",
        "Dockerfile",
        "docker-compose*.yml",
        "**/.env*",
    )
    allowed_commands: tuple[str, ...] = (
        "pytest",
        "pytest tests",
        "npm test",
        "npm run test",
        "npm run lint",
        "npm run typecheck",
        "pnpm test",
        "ruff check .",
        "mypy .",
        "go test ./...",
        "python -m pytest",
        "python3 -m pytest",
    )
    blocked_command_fragments: tuple[str, ...] = (
        "rm -rf",
        "curl ",
        "wget ",
        "printenv",
        "cat .env",
        "cat */secrets",
        "sudo ",
        "chmod 777",
        "docker run",
    )


@dataclass
class PolicyEngine:
    config: PolicyConfig = field(default_factory=PolicyConfig)

    def evaluate_plan(self, plan: ImplementationPlan) -> PolicyDecision:
        if len(plan.files_to_modify) > self.config.max_files_changed_without_approval:
            return PolicyDecision(
                decision=PolicyDecisionType.ESCALATE,
                reason="Plan modifies more files than the default low-risk threshold.",
                required_approvals=["maintainer"],
            )

        high_risk_files = [path for path in plan.files_to_modify if self._is_high_risk_file(path)]
        if high_risk_files:
            return PolicyDecision(
                decision=PolicyDecisionType.ESCALATE,
                reason="Plan touches high-risk files and needs explicit maintainer approval.",
                required_approvals=["maintainer"],
                blocked_patterns=high_risk_files,
            )

        blocked_commands = [command for command in plan.commands_to_run if not self.is_command_allowed(command)]
        if blocked_commands:
            return PolicyDecision(
                decision=PolicyDecisionType.DENY,
                reason="Plan contains commands outside the allowlist.",
                blocked_patterns=blocked_commands,
            )

        return PolicyDecision(decision=PolicyDecisionType.ALLOW, reason="Plan is within low-risk policy limits.")

    def is_command_allowed(self, command: str) -> bool:
        normalized = " ".join(shlex.split(command))
        lowered = normalized.lower()
        if any(fragment in lowered for fragment in self.config.blocked_command_fragments):
            return False
        return any(normalized == allowed or normalized.startswith(f"{allowed} ") for allowed in self.config.allowed_commands)

    def evaluate_command(self, command: str) -> PolicyDecision:
        if self.is_command_allowed(command):
            return PolicyDecision(decision=PolicyDecisionType.ALLOW, reason="Command is allowlisted.")
        return PolicyDecision(decision=PolicyDecisionType.DENY, reason="Command is not allowlisted.", blocked_patterns=[command])

    def _is_high_risk_file(self, path: str) -> bool:
        normalized = path.replace("\\", "/")
        return any(fnmatch.fnmatch(normalized, pattern) for pattern in self.config.high_risk_patterns)
