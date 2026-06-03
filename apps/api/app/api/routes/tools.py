from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.tools import ToolExecutor, get_tool_registry

router = APIRouter()


@router.get("")
async def list_tools(
    run_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    if run_id is None:
        tools = get_tool_registry().definitions()
    else:
        tools = await ToolExecutor().available_tools(db, run_id=run_id)
    return {"tools": [tool.model_dump(mode="json") for tool in tools]}
