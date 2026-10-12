from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.home import HomeOverview
from app.services.home_service import get_home_overview

router = APIRouter(prefix='/home', tags=['Home'])


@router.get('/overview', response_model=HomeOverview)
def overview(response: Response, db: Session = Depends(get_db)) -> HomeOverview:
    response.headers['Cache-Control'] = 'public, max-age=60, s-maxage=300'
    return get_home_overview(db)
