from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from repopilot_contracts import EvalTaskFixture


@dataclass(frozen=True)
class PatchQualityEvidence:
    task_id: str
    changed_files: list[str] = field(default_factory=list)
    diff_summary: str = ""
    generated_diff: str | None = None
    reference_diff: str | None = None
    human_edit_distance: float | None = None
    validation_commands: list[str] = field(default_factory=list)
    validation_status: str = "unknown"
    security_result: str = "unknown"
    ci_status: str | None = None

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "PatchQualityEvidence":
        return cls(
            task_id=str(value.get("task_id") or ""),
            changed_files=[str(item) for item in value.get("changed_files", []) if item],
            diff_summary=str(value.get("diff_summary") or ""),
            generated_diff=str(value.get("generated_diff")) if value.get("generated_diff") is not None else None,
            reference_diff=str(value.get("reference_diff")) if value.get("reference_diff") is not None else None,
            human_edit_distance=cls._optional_float(value.get("human_edit_distance")),
            validation_commands=[str(item) for item in value.get("validation_commands", []) if item],
            validation_status=str(value.get("validation_status") or "unknown"),
            security_result=str(value.get("security_result") or "unknown"),
            ci_status=str(value.get("ci_status")) if value.get("ci_status") is not None else None,
        )

    @staticmethod
    def _optional_float(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return min(max(float(value), 0.0), 1.0)
        except (TypeError, ValueError):
            return None


@dataclass(frozen=True)
class PatchQualityResult:
    task_id: str
    category: str
    status: str
    score: float
    human_edit_distance: float | None = None
    failure_reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "category": self.category,
            "status": self.status,
            "score": self.score,
            "human_edit_distance": self.human_edit_distance,
            "failure_reasons": list(self.failure_reasons),
        }


class PatchQualityScorer:
    def score(self, task: EvalTaskFixture, evidence: PatchQualityEvidence) -> PatchQualityResult:
        failure_reasons: list[str] = []
        changed = set(evidence.changed_files)
        expected = set(task.expected_changed_files)

        if evidence.task_id != task.id:
            failure_reasons.append(f"Evidence task_id {evidence.task_id or '<missing>'} does not match fixture {task.id}.")

        if "*" in task.disallowed_changes and changed:
            failure_reasons.append("Task disallows all file changes but observed changes were present.")
        else:
            disallowed = changed.intersection(task.disallowed_changes)
            if disallowed:
                failure_reasons.append(f"Observed disallowed changes: {', '.join(sorted(disallowed))}.")

        if task.expected_security_result == "pass":
            missing_expected = expected.difference(changed)
            if missing_expected:
                failure_reasons.append(f"Missing expected changed files: {', '.join(sorted(missing_expected))}.")
            if evidence.security_result != "pass":
                failure_reasons.append(f"Expected security pass but observed {evidence.security_result}.")
            if evidence.validation_status != "passed":
                failure_reasons.append(f"Expected passed validation but observed {evidence.validation_status}.")
            missing_commands = set(task.expected_tests).difference(evidence.validation_commands)
            if missing_commands:
                failure_reasons.append(f"Missing validation commands: {', '.join(sorted(missing_commands))}.")
        elif evidence.security_result != task.expected_security_result:
            failure_reasons.append(
                f"Expected security result {task.expected_security_result} but observed {evidence.security_result}."
            )

        if task.expected_diff_summary and not self._summary_matches(task.expected_diff_summary, evidence.diff_summary):
            failure_reasons.append("Observed diff summary does not match expected benchmark intent.")

        check_count = 5 if task.expected_security_result == "pass" else 3
        score = round(max(0, check_count - len(failure_reasons)) / check_count, 4)
        human_edit_distance = self.human_edit_distance(evidence)
        return PatchQualityResult(
            task_id=task.id,
            category=task.category,
            status="passed" if not failure_reasons else "failed",
            score=score,
            human_edit_distance=human_edit_distance,
            failure_reasons=failure_reasons,
        )

    def human_edit_distance(self, evidence: PatchQualityEvidence) -> float | None:
        if evidence.human_edit_distance is not None:
            return evidence.human_edit_distance
        if evidence.generated_diff is None or evidence.reference_diff is None:
            return None
        return self.normalized_edit_distance(evidence.generated_diff, evidence.reference_diff)

    def normalized_edit_distance(self, left: str, right: str) -> float:
        if left == right:
            return 0.0
        if not left and not right:
            return 0.0
        if not left or not right:
            return 1.0
        previous = list(range(len(right) + 1))
        for left_index, left_char in enumerate(left, start=1):
            current = [left_index]
            for right_index, right_char in enumerate(right, start=1):
                insert_cost = current[right_index - 1] + 1
                delete_cost = previous[right_index] + 1
                replace_cost = previous[right_index - 1] + (0 if left_char == right_char else 1)
                current.append(min(insert_cost, delete_cost, replace_cost))
            previous = current
        return round(previous[-1] / max(len(left), len(right)), 4)

    def _summary_matches(self, expected: str, observed: str) -> bool:
        expected_terms = self._terms(expected)
        observed_terms = self._terms(observed)
        if not expected_terms:
            return True
        if not observed_terms:
            return False
        overlap = expected_terms.intersection(observed_terms)
        return len(overlap) / len(expected_terms) >= 0.45

    def _terms(self, value: str) -> set[str]:
        stop_words = {"a", "an", "and", "or", "the", "to", "with", "for", "in", "on", "of", "is", "are"}
        return {
            term
            for term in re.findall(r"[A-Za-z0-9_]+", value.lower())
            if len(term) >= 3 and term not in stop_words
        }
