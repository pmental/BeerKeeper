from fastapi import APIRouter

from app.beer_styles import get_beer_styles

router = APIRouter(prefix="/api/beer-styles", tags=["beer-styles"])


@router.get("")
def list_beer_styles():
    return {"styles": get_beer_styles()}
