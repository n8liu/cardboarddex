from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.home import HomeOverview
from app.services.home_service import build_home_overview
from app.common.response_cache import cached_read

router = APIRouter(prefix='/home', tags=['Home'])


@router.get('/overview', response_model=HomeOverview)
@cached_read("home", fresh=300, maximum=1800)
def overview(response: Response, db: Session = Depends(get_db)) -> HomeOverview:
    return build_home_overview(db)
