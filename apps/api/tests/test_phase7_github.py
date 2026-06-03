from __future__ import annotations

import asyncio
import json
from uuid import uuid4

from repopilot_github_client import command_permission_decision, role_for_github_permission as package_role_for_github_permission

from app.db.models import Installation, Repository
from app.services.github_app import GitHubApiClient
from app.services.github_permissions import GitHubPermissionService, role_for_github_permission


class FakeGitHubClient:
    def __init__(self, permission: str) -> None:
        self.permission = permission

    async def get_collaborator_permission(self, **_kwargs) -> str:
        return self.permission


class FakeTokenProvider:
    def is_configured(self) -> bool:
        return True

    async def create_installation_access_token(self, _installation_id: str) -> str:
        return "installation-token"


def test_github_permission_mapping() -> None:
    assert role_for_github_permission is package_role_for_github_permission
    assert role_for_github_permission("admin") == "admin"
    assert role_for_github_permission("maintain") == "maintainer"
    assert role_for_github_permission("write") == "write"
    assert role_for_github_permission("triage") == "triage"
    assert role_for_github_permission("read") == "read"


def test_github_command_permission_decision_comes_from_package() -> None:
    decision = command_permission_decision(github_permission="triage", command="revise")

    assert decision.allowed is True
    assert decision.repopilot_role == "triage"


def test_github_command_permission_allows_write_approve() -> None:
    installation = Installation(id=uuid4(), github_installation_id="123", account_name="octo")
    repository = Repository(id=uuid4(), installation_id=installation.id, owner="octo", name="demo")

    decision = asyncio.run(
        GitHubPermissionService(client=FakeGitHubClient("write")).check_command_permission(
            installation=installation,
            repository=repository,
            username="alice",
            command="approve",
        )
    )

    assert decision.allowed is True
    assert decision.repopilot_role == "write"


def test_github_command_permission_requires_maintainer_for_escalated_approval() -> None:
    installation = Installation(id=uuid4(), github_installation_id="123", account_name="octo")
    repository = Repository(id=uuid4(), installation_id=installation.id, owner="octo", name="demo")

    decision = asyncio.run(
        GitHubPermissionService(client=FakeGitHubClient("write")).check_command_permission(
            installation=installation,
            repository=repository,
            username="alice",
            command="approve",
            escalated=True,
        )
    )

    assert decision.allowed is False
    assert "maintainer" in decision.reason


def test_github_client_fetches_code_scanning_alerts(monkeypatch) -> None:
    from app.services import github_app

    class FakeResponse:
        status_code = 200
        text = "[]"
        content = b"[]"

        def json(self):
            return [{"number": 7, "state": "open", "rule": {"id": "js/xss"}}]

    class FakeAsyncClient:
        last_url = ""
        last_headers = {}

        def __init__(self, **_kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url, headers):
            FakeAsyncClient.last_url = url
            FakeAsyncClient.last_headers = headers
            return FakeResponse()

    monkeypatch.setattr(github_app.httpx, "AsyncClient", FakeAsyncClient)

    alerts = asyncio.run(
        GitHubApiClient(token_provider=FakeTokenProvider()).fetch_code_scanning_alerts(
            installation_id="123",
            owner="octo",
            repo="demo",
            ref="refs/heads/repopilot/fix",
            per_page=500,
        )
    )

    assert alerts[0]["number"] == 7
    assert "/repos/octo/demo/code-scanning/alerts?" in FakeAsyncClient.last_url
    assert "per_page=100" in FakeAsyncClient.last_url
    assert "tool_name=CodeQL" in FakeAsyncClient.last_url
    assert "Authorization" in FakeAsyncClient.last_headers


def test_github_client_summarizes_check_runs_with_redaction_and_bounds() -> None:
    secret = "sk-live-secret-value-1234567890"
    payload = {
        "total_count": 2,
        "check_runs": [
            {
                "id": 101,
                "name": "pytest",
                "status": "completed",
                "conclusion": "failure",
                "html_url": "https://github.com/octo/demo/runs/101",
                "details_url": "https://github.com/octo/demo/actions/runs/101",
                "output": {
                    "title": "Tests failed",
                    "summary": f"ERROR tests failed with TOKEN={secret}",
                    "text": "Traceback line " * 40,
                    "annotations_count": 1,
                },
            },
            {"id": 102, "name": "lint", "status": "completed", "conclusion": "success", "output": {}},
        ],
    }

    summary = GitHubApiClient(token_provider=FakeTokenProvider()).summarize_check_runs(payload, max_text_chars=80)

    assert summary["total_count"] == 2
    assert summary["returned_count"] == 2
    first = summary["check_runs"][0]
    assert first["annotations_count"] == 1
    assert first["output_summary"] == "ERROR tests failed with TOKEN=[REDACTED_SECRET]"
    assert len(first["output_text"]) <= 80
    assert secret not in json.dumps(summary)


def test_github_client_summarizes_check_annotations_with_redaction() -> None:
    secret = "sk-live-secret-value-1234567890"
    annotations = [
        {
            "path": "tests/test_demo.py",
            "start_line": 12,
            "end_line": 12,
            "annotation_level": "failure",
            "title": "pytest failure",
            "message": f"Assertion failed with TOKEN={secret}",
            "raw_details": "Detailed traceback " * 40,
        }
    ]

    summary = GitHubApiClient(token_provider=FakeTokenProvider()).summarize_check_annotations(
        annotations,
        max_text_chars=90,
    )

    assert summary[0]["path"] == "tests/test_demo.py"
    assert summary[0]["message"] == "Assertion failed with TOKEN=[REDACTED_SECRET]"
    assert len(summary[0]["raw_details"]) <= 90
    assert secret not in json.dumps(summary)


def test_github_client_fetches_check_run_annotations(monkeypatch) -> None:
    from app.services import github_app

    class FakeResponse:
        status_code = 200
        text = "[]"
        content = b"[]"

        def json(self):
            return [{"path": "tests/test_demo.py", "annotation_level": "failure", "message": "failed"}]

    class FakeAsyncClient:
        last_url = ""
        last_headers = {}

        def __init__(self, **_kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url, headers):
            FakeAsyncClient.last_url = url
            FakeAsyncClient.last_headers = headers
            return FakeResponse()

    monkeypatch.setattr(github_app.httpx, "AsyncClient", FakeAsyncClient)

    annotations = asyncio.run(
        GitHubApiClient(token_provider=FakeTokenProvider()).fetch_check_run_annotations(
            installation_id="123",
            owner="octo",
            repo="demo",
            check_run_id=101,
            per_page=500,
        )
    )

    assert annotations[0]["path"] == "tests/test_demo.py"
    assert "/repos/octo/demo/check-runs/101/annotations?" in FakeAsyncClient.last_url
    assert "per_page=100" in FakeAsyncClient.last_url
    assert "Authorization" in FakeAsyncClient.last_headers


def test_github_client_fetches_workflow_logs_as_safe_metadata(monkeypatch) -> None:
    from app.services import github_app

    secret = "sk-live-secret-value-1234567890"
    body = f"Run tests\nERROR failed with TOKEN={secret}".encode()

    class FakeResponse:
        status_code = 200
        text = ""
        content = body
        headers = {"content-type": "application/zip"}

    class FakeAsyncClient:
        last_url = ""
        last_headers = {}
        last_follow_redirects = False

        def __init__(self, **kwargs) -> None:
            FakeAsyncClient.last_follow_redirects = bool(kwargs.get("follow_redirects"))

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url, headers):
            FakeAsyncClient.last_url = url
            FakeAsyncClient.last_headers = headers
            return FakeResponse()

    monkeypatch.setattr(github_app.httpx, "AsyncClient", FakeAsyncClient)

    result = asyncio.run(
        GitHubApiClient(token_provider=FakeTokenProvider()).fetch_workflow_logs(
            installation_id="123",
            owner="octo",
            repo="demo",
            run_id=987,
        )
    )

    assert result["run_id"] == 987
    assert result["byte_size"] == len(body)
    assert result["content_type"] == "application/zip"
    assert len(result["sha256"]) == 64
    assert "TOKEN=[REDACTED_SECRET]" in result["redacted_text_excerpt"]
    assert secret not in json.dumps(result)
    assert "/repos/octo/demo/actions/runs/987/logs" in FakeAsyncClient.last_url
    assert FakeAsyncClient.last_follow_redirects is True
    assert "Authorization" in FakeAsyncClient.last_headers
