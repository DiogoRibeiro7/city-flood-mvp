from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.api.openapi_examples import RESP_INVALID_ARGUMENT, error_response
from floodmvp.models.domain import CityOut
from floodmvp.storage.db import get_session
from floodmvp.storage.repos.assets import get_city, list_cities

router = APIRouter(tags=["cities"])


@router.get(
    "/cities",
    response_model=list[CityOut],
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": [
                        {"city_id": "city_porto_mvp", "name": "MVP City", "country": "PT"}
                    ]
                }
            }
        }
        ,
        400: RESP_INVALID_ARGUMENT,
    },
)
async def cities(session: AsyncSession = Depends(get_session)) -> list[CityOut]:
    rows = await list_cities(session)
    return [CityOut(city_id=c.city_id, name=c.name, country=c.country) for c in rows]


@router.get(
    "/cities/{city_id}",
    response_model=CityOut,
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {"city_id": "city_porto_mvp", "name": "MVP City", "country": "PT"}
                }
            }
        }
        ,
        404: error_response(
            code="CITY_NOT_FOUND",
            message="City not found",
            details={"city_id": "city_missing"},
        ),
    },
)
async def city(city_id: str, session: AsyncSession = Depends(get_session)) -> CityOut:
    c = await get_city(session, city_id)
    if c is None:
        from floodmvp.common.errors import AppError
        raise AppError(
            code="CITY_NOT_FOUND",
            message="City not found",
            details={"city_id": city_id},
            status_code=404,
        )
    return CityOut(city_id=c.city_id, name=c.name, country=c.country)
