from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx

from app.core.config import Settings, settings
from app.services.security_envelope import redact_text


MAX_CHECK_RUN_SUMMARIES = 20
MAX_CHECK_ANNOTATION_SUMMARIES = 20
MAX_CHECK_OUTPUT_CHARS = 1200


class GitHubIntegrationError(RuntimeError):
    pass


class GitHubCredentialsMissing(GitHubIntegrationError):
    pass


class GitHubWritesDisabled(GitHubIntegrationError):
    pass


class GitHubAppTokenProvider:
    def __init__(self, config: Settings | None = None) -> None:
        self.config = config or settings

    def is_configured(self) -> bool:
        return bool(self.config.github_app_id and self._private_key_material())

    def create_app_jwt(self) -> str:
        if not self.is_configured():
            raise GitHubCredentialsMissing(
                "GitHub App credentials are not configured. Set GITHUB_APP_ID and GITHUB_APP_PRIVATE_KEY or GITHUB_PRIVATE_KEY_PATH."
            )

        try:
            import jwt
        except ImportError as exc:
            raise GitHubIntegrationError(
                "PyJWT is required for GitHub App JWT signing. Install the API requirements after adding credentials."
            ) from exc

        now = int(time.time())
        payload = {
            "iat": now - 60,
            "exp": now + 9 * 60,
            "iss": self.config.github_app_id,
        }
        return jwt.encode(payload, self._private_key_material(), algorithm="RS256")

    async def create_installation_access_token(self, installation_id: str) -> str:
        app_jwt = self.create_app_jwt()
        url = f"{self.config.github_api_base_url.rstrip('/')}/app/installations/{installation_id}/access_tokens"
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                url,
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {app_jwt}",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
        if response.status_code >= 400:
            raise GitHubIntegrationError(f"GitHub installation token request failed: {response.status_code} {response.text[:240]}")
        token = response.json().get("token")
        if not token:
            raise GitHubIntegrationError("GitHub installation token response did not include a token.")
        return str(token)

    def _private_key_material(self) -> str | None:
        if self.config.github_private_key:
            return self.config.github_private_key.replace("\\n", "\n")
        if self.config.github_private_key_path:
            path = Path(self.config.github_private_key_path).expanduser()
            if path.is_file():
                return path.read_text(encoding="utf-8")
        return None


class GitHubApiClient:
    def __init__(self, token_provider: GitHubAppTokenProvider | None = None, config: Settings | None = None) -> None:
        self.config = config or settings
        self.token_provider = token_provider or GitHubAppTokenProvider(self.config)

    def ensure_write_mode(self) -> None:
        if not self.config.github_writes_enabled:
            raise GitHubWritesDisabled(
                "GitHub writes are disabled. Set GITHUB_WRITES_ENABLED=true after configuring GitHub App credentials."
            )
        if not self.token_provider.is_configured():
            raise GitHubCredentialsMissing(
                "GitHub writes require GITHUB_APP_ID and a GitHub App private key."
            )

    async def request(
        self,
        *,
        installation_id: str,
        method: str,
        path: str,
        json_body: dict[str, Any] | None = None,
        require_write: bool = True,
    ) -> dict[str, Any]:
        if require_write:
            self.ensure_write_mode()
        elif not self.token_provider.is_configured():
            raise GitHubCredentialsMissing("GitHub App credentials are required for this GitHub API call.")
        token = await self.token_provider.create_installation_access_token(installation_id)
        url = f"{self.config.github_api_base_url.rstrip('/')}/{path.lstrip('/')}"
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.request(
                method,
                url,
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {token}",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                json=json_body,
            )
        if response.status_code >= 400:
            raise GitHubIntegrationError(f"GitHub API request failed: {response.status_code} {response.text[:300]}")
        if not response.content:
            return {}
        return dict(response.json())

    async def get_ref_sha(self, *, installation_id: str, owner: str, repo: str, branch: str) -> str:
        payload = await self.request(
            installation_id=installation_id,
            method="GET",
            path=f"/repos/{owner}/{repo}/git/ref/heads/{branch}",
        )
        sha = payload.get("object", {}).get("sha") if isinstance(payload.get("object"), dict) else None
        if not sha:
            raise GitHubIntegrationError("GitHub ref response did not include object.sha.")
        return str(sha)

    async def create_branch(self, *, installation_id: str, owner: str, repo: str, branch_name: str, base_sha: str) -> dict[str, Any]:
        return await self.request(
            installation_id=installation_id,
            method="POST",
            path=f"/repos/{owner}/{repo}/git/refs",
            json_body={"ref": f"refs/heads/{branch_name}", "sha": base_sha},
        )

    async def get_file(self, *, installation_id: str, owner: str, repo: str, path: str, ref: str) -> dict[str, Any]:
        return await self.request(
            installation_id=installation_id,
            method="GET",
            path=f"/repos/{owner}/{repo}/contents/{path}?ref={ref}",
            require_write=False,
        )

    async def get_commit(self, *, installation_id: str, owner: str, repo: str, commit_sha: str) -> dict[str, Any]:
        return await self.request(
            installation_id=installation_id,
            method="GET",
            path=f"/repos/{owner}/{repo}/git/commits/{commit_sha}",
        )

    async def create_blob(self, *, installation_id: str, owner: str, repo: str, content: str) -> str:
        payload = await self.request(
            installation_id=installation_id,
            method="POST",
            path=f"/repos/{owner}/{repo}/git/blobs",
            json_body={"content": content, "encoding": "utf-8"},
        )
        sha = payload.get("sha")
        if not sha:
            raise GitHubIntegrationError("GitHub blob response did not include sha.")
        return str(sha)

    async def create_tree(
        self,
        *,
        installation_id: str,
        owner: str,
        repo: str,
        base_tree_sha: str,
        tree_items: list[dict[str, Any]],
    ) -> str:
        payload = await self.request(
            installation_id=installation_id,
            method="POST",
            path=f"/repos/{owner}/{repo}/git/trees",
            json_body={"base_tree": base_tree_sha, "tree": tree_items},
        )
        sha = payload.get("sha")
        if not sha:
            raise GitHubIntegrationError("GitHub tree response did not include sha.")
        return str(sha)

    async def create_commit(
        self,
        *,
        installation_id: str,
        owner: str,
        repo: str,
        message: str,
        tree_sha: str,
        parent_sha: str,
    ) -> str:
        payload = await self.request(
            installation_id=installation_id,
            method="POST",
            path=f"/repos/{owner}/{repo}/git/commits",
            json_body={"message": message, "tree": tree_sha, "parents": [parent_sha]},
        )
        sha = payload.get("sha")
        if not sha:
            raise GitHubIntegrationError("GitHub commit response did not include sha.")
        return str(sha)

    async def update_ref(self, *, installation_id: str, owner: str, repo: str, branch_name: str, commit_sha: str) -> dict[str, Any]:
        return await self.request(
            installation_id=installation_id,
            method="PATCH",
            path=f"/repos/{owner}/{repo}/git/refs/heads/{branch_name}",
            json_body={"sha": commit_sha, "force": False},
        )

    async def commit_patch(
        self,
        *,
        installation_id: str,
        owner: str,
        repo: str,
        branch_name: str,
        message: str,
        changed_files: list[dict[str, str | None]],
    ) -> str:
        parent_sha = await self.get_ref_sha(installation_id=installation_id, owner=owner, repo=repo, branch=branch_name)
        commit = await self.get_commit(installation_id=installation_id, owner=owner, repo=repo, commit_sha=parent_sha)
        tree = commit.get("tree") if isinstance(commit.get("tree"), dict) else {}
        base_tree_sha = str(tree.get("sha") or "")
        if not base_tree_sha:
            raise GitHubIntegrationError("GitHub commit response did not include tree.sha.")

        tree_items: list[dict[str, Any]] = []
        for file in changed_files:
            path = str(file["path"])
            content = file.get("content")
            if content is None:
                tree_items.append({"path": path, "mode": "100644", "type": "blob", "sha": None})
                continue
            blob_sha = await self.create_blob(installation_id=installation_id, owner=owner, repo=repo, content=content)
            tree_items.append({"path": path, "mode": "100644", "type": "blob", "sha": blob_sha})

        tree_sha = await self.create_tree(
            installation_id=installation_id,
            owner=owner,
            repo=repo,
            base_tree_sha=base_tree_sha,
            tree_items=tree_items,
        )
        commit_sha = await self.create_commit(
            installation_id=installation_id,
            owner=owner,
            repo=repo,
            message=message,
            tree_sha=tree_sha,
            parent_sha=parent_sha,
        )
        await self.update_ref(
            installation_id=installation_id,
            owner=owner,
            repo=repo,
            branch_name=branch_name,
            commit_sha=commit_sha,
        )
        return commit_sha

    async def open_pull_request(
        self,
        *,
        installation_id: str,
        owner: str,
        repo: str,
        branch_name: str,
        base_branch: str,
        title: str,
        body: str,
        draft: bool = True,
    ) -> dict[str, Any]:
        return await self.request(
            installation_id=installation_id,
            method="POST",
            path=f"/repos/{owner}/{repo}/pulls",
            json_body={"head": branch_name, "base": base_branch, "title": title, "body": body, "draft": draft},
        )

    async def comment_issue(
        self,
        *,
        installation_id: str,
        owner: str,
        repo: str,
        issue_number: int,
        body: str,
    ) -> dict[str, Any]:
        return await self.request(
            installation_id=installation_id,
            method="POST",
            path=f"/repos/{owner}/{repo}/issues/{issue_number}/comments",
            json_body={"body": body},
        )

    async def fetch_check_runs(self, *, installation_id: str, owner: str, repo: str, ref: str) -> dict[str, Any]:
        return await self.request(
            installation_id=installation_id,
            method="GET",
            path=f"/repos/{owner}/{repo}/commits/{ref}/check-runs",
            require_write=False,
        )

    async def fetch_workflow_logs(self, *, installation_id: str, owner: str, repo: str, run_id: int) -> dict[str, Any]:
        if not self.token_provider.is_configured():
            raise GitHubCredentialsMissing("GitHub App credentials are required for workflow log fetches.")
        token = await self.token_provider.create_installation_access_token(installation_id)
        url = f"{self.config.github_api_base_url.rstrip('/')}/repos/{owner}/{repo}/actions/runs/{run_id}/logs"
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            response = await client.get(
                url,
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {token}",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
        if response.status_code >= 400:
            raise GitHubIntegrationError(f"GitHub workflow logs request failed: {response.status_code} {response.text[:300]}")
        content = response.content or b""
        return {
            "run_id": run_id,
            "byte_size": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
            "content_type": response.headers.get("content-type", "application/octet-stream"),
            "redacted_text_excerpt": self._bounded_redacted(content.decode("utf-8", errors="ignore"), max_chars=MAX_CHECK_OUTPUT_CHARS),
        }

    async def fetch_check_run_annotations(
        self,
        *,
        installation_id: str,
        owner: str,
        repo: str,
        check_run_id: int,
        per_page: int = 50,
    ) -> list[dict[str, Any]]:
        if not self.token_provider.is_configured():
            raise GitHubCredentialsMissing("GitHub App credentials are required for check-run annotation fetches.")
        query = urlencode({"per_page": min(max(per_page, 1), 100)})
        token = await self.token_provider.create_installation_access_token(installation_id)
        url = f"{self.config.github_api_base_url.rstrip('/')}/repos/{owner}/{repo}/check-runs/{check_run_id}/annotations?{query}"
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                url,
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {token}",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
        if response.status_code >= 400:
            raise GitHubIntegrationError(f"GitHub check-run annotations request failed: {response.status_code} {response.text[:300]}")
        payload = response.json()
        if not isinstance(payload, list):
            raise GitHubIntegrationError("GitHub check-run annotations response was not an array.")
        return [dict(item) for item in payload if isinstance(item, dict)]

    def summarize_check_runs(
        self,
        payload: dict[str, Any],
        *,
        max_checks: int = MAX_CHECK_RUN_SUMMARIES,
        max_text_chars: int = MAX_CHECK_OUTPUT_CHARS,
    ) -> dict[str, Any]:
        check_runs = payload.get("check_runs")
        if not isinstance(check_runs, list):
            check_runs = []
        summaries: list[dict[str, Any]] = []
        for check in check_runs[:max(max_checks, 0)]:
            if not isinstance(check, dict):
                continue
            output = check.get("output") if isinstance(check.get("output"), dict) else {}
            summaries.append(
                {
                    "id": check.get("id"),
                    "name": self._bounded_redacted(check.get("name"), max_chars=160),
                    "status": check.get("status"),
                    "conclusion": check.get("conclusion"),
                    "html_url": check.get("html_url"),
                    "details_url": check.get("details_url"),
                    "started_at": check.get("started_at"),
                    "completed_at": check.get("completed_at"),
                    "annotations_count": self._safe_int(output.get("annotations_count")),
                    "output_title": self._bounded_redacted(output.get("title"), max_chars=240),
                    "output_summary": self._bounded_redacted(output.get("summary"), max_chars=max_text_chars),
                    "output_text": self._bounded_redacted(output.get("text"), max_chars=max_text_chars),
                }
            )
        return {
            "total_count": self._safe_int(payload.get("total_count"), default=len(check_runs)),
            "returned_count": len(summaries),
            "truncated": len(check_runs) > len(summaries),
            "check_runs": summaries,
        }

    def summarize_check_annotations(
        self,
        annotations: list[dict[str, Any]],
        *,
        max_annotations: int = MAX_CHECK_ANNOTATION_SUMMARIES,
        max_text_chars: int = MAX_CHECK_OUTPUT_CHARS,
    ) -> list[dict[str, Any]]:
        summaries: list[dict[str, Any]] = []
        for annotation in annotations[:max(max_annotations, 0)]:
            summaries.append(
                {
                    "path": self._bounded_redacted(annotation.get("path"), max_chars=500),
                    "start_line": annotation.get("start_line"),
                    "end_line": annotation.get("end_line"),
                    "annotation_level": annotation.get("annotation_level"),
                    "title": self._bounded_redacted(annotation.get("title"), max_chars=240),
                    "message": self._bounded_redacted(annotation.get("message"), max_chars=max_text_chars),
                    "raw_details": self._bounded_redacted(annotation.get("raw_details"), max_chars=max_text_chars),
                }
            )
        return summaries

    async def get_collaborator_permission(
        self,
        *,
        installation_id: str,
        owner: str,
        repo: str,
        username: str,
    ) -> str:
        payload = await self.request(
            installation_id=installation_id,
            method="GET",
            path=f"/repos/{owner}/{repo}/collaborators/{username}/permission",
            require_write=False,
        )
        permission = payload.get("permission")
        if not permission:
            raise GitHubIntegrationError("GitHub permission response did not include permission.")
        return str(permission)

    def _bounded_redacted(self, value: Any, *, max_chars: int) -> str:
        if value is None:
            return ""
        redacted = redact_text(str(value))
        if len(redacted) <= max_chars:
            return redacted
        if max_chars <= 3:
            return redacted[:max_chars]
        return f"{redacted[: max_chars - 3]}..."

    def _safe_int(self, value: Any, *, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    async def fetch_code_scanning_alerts(
        self,
        *,
        installation_id: str,
        owner: str,
        repo: str,
        state: str = "open",
        ref: str | None = None,
        tool_name: str = "CodeQL",
        per_page: int = 100,
    ) -> list[dict[str, Any]]:
        if not self.token_provider.is_configured():
            raise GitHubCredentialsMissing("GitHub App credentials are required for CodeQL alert fetches.")
        query: dict[str, str | int] = {"state": state, "per_page": min(max(per_page, 1), 100)}
        if ref:
            query["ref"] = ref
        if tool_name:
            query["tool_name"] = tool_name
        token = await self.token_provider.create_installation_access_token(installation_id)
        url = (
            f"{self.config.github_api_base_url.rstrip('/')}/repos/{owner}/{repo}/code-scanning/alerts?"
            f"{urlencode(query)}"
        )
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                url,
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {token}",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
        if response.status_code >= 400:
            raise GitHubIntegrationError(f"GitHub code-scanning alerts request failed: {response.status_code} {response.text[:300]}")
        payload = response.json()
        if not isinstance(payload, list):
            raise GitHubIntegrationError("GitHub code-scanning alerts response was not an array.")
        return [dict(item) for item in payload if isinstance(item, dict)]
