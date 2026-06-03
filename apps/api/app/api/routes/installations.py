from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Installation, Repository
from app.db.session import get_db

router = APIRouter()


@router.get("")
async def list_installations(db: AsyncSession = Depends(get_db)) -> list[dict[str, object]]:
    result = await db.execute(select(Installation).order_by(Installation.created_at.desc()))
    installations = result.scalars().all()
    response: list[dict[str, object]] = []
    for installation in installations:
        repo_count = await db.scalar(
            select(func.count()).select_from(Repository).where(Repository.installation_id == installation.id)
        )
        response.append(
            {
                "id": str(installation.id),
                "github_installation_id": installation.github_installation_id,
                "account_name": installation.account_name,
                "repository_count": repo_count or 0,
                "created_at": installation.created_at,
            }
        )
    return response
