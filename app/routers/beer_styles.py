from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import models
from app.database import get_db

router = APIRouter(prefix="/api/beer-styles", tags=["beer-styles"])


@router.get("")
def list_beer_styles(db: Session = Depends(get_db)):
    names = [
        name
        for (name,) in db.query(models.BeerStyle.name).order_by(models.BeerStyle.sort_order, models.BeerStyle.name).all()
    ]
    return {"styles": names}
