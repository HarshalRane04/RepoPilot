from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Installation, Repository
from app.db.session import get_db
from app.services.auth import CurrentUser, get_current_user
from app.services.authorization import require_role

router = APIRouter()


@router.get("")
async def list_installations(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, object]]:
    require_role(current_user, "viewer")
    result = await db.execute(select(Installation).order_by(Installation.created_at.desc()))
    installations = result.scalars().all()
    repository_result = await db.execute(select(Repository))
    repository_keys_by_installation: dict[str, set[str]] = {}
    for repository in repository_result.scalars().all():
        repository_keys_by_installation.setdefault(str(repository.installation_id), set()).add(
            _canonical_repository_id(repository.owner, repository.name)
        )
    responses: list[dict[str, object]] = []
    for installation in installations:
        installation_id = str(installation.id)
        responses.append(
            {
                "id": installation_id,
                "github_installation_id": installation.github_installation_id,
                "account_name": installation.account_name,
                "repository_count": len(repository_keys_by_installation.get(installation_id, set())),
                "created_at": installation.created_at,
                "source_mode": (
                    "oauth_discovery"
                    if installation.github_installation_id.startswith("oauth:")
                    else "github_app"
                ),
                "_repository_keys": repository_keys_by_installation.get(installation_id, set()),
            }
        )
    return _canonicalize_installation_responses(responses)


def _canonicalize_installation_responses(
    responses: list[dict[str, object]],
) -> list[dict[str, object]]:
    groups: dict[str, list[dict[str, object]]] = {}
    for response in responses:
        canonical_id = str(response["account_name"]).strip().casefold()
        groups.setdefault(canonical_id, []).append(response)

    canonical: list[dict[str, object]] = []
    for canonical_id, aliases in groups.items():
        preferred = max(
            aliases,
            key=lambda item: (
                item.get("source_mode") == "github_app",
                str(item.get("created_at") or ""),
            ),
        )
        repository_keys: set[str] = set()
        for alias in aliases:
            raw_keys = alias.get("_repository_keys", set())
            if isinstance(raw_keys, set):
                repository_keys.update(str(key) for key in raw_keys)
        merged = {key: value for key, value in preferred.items() if key != "_repository_keys"}
        merged.update(
            {
                "canonical_id": canonical_id,
                "alias_ids": [
                    str(preferred["id"]),
                    *sorted(str(item["id"]) for item in aliases if item is not preferred),
                ],
                "github_installation_ids": sorted(
                    {str(item["github_installation_id"]) for item in aliases}
                ),
                "source_modes": sorted({str(item["source_mode"]) for item in aliases}),
                "repository_count": len(repository_keys),
            }
        )
        canonical.append(merged)
    return canonical


def _canonical_repository_id(owner: str, name: str) -> str:
    return f"{owner.strip().casefold()}/{name.strip().casefold()}"
