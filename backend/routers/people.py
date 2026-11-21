from typing import List
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models.domain import Person
from backend.schemas.domain import PersonRead
from backend.services.digest_service import DigestService

router = APIRouter(tags=["people & digests"])

@router.get("/people", response_model=List[PersonRead])
def list_people(db: Session = Depends(get_db)):
    return db.query(Person).all()

@router.get("/people/{person_id}/digest")
def get_person_digest(person_id: int, db: Session = Depends(get_db)):
    try:
        return DigestService.generate_digest_for_person(db, person_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/digest/generate")
def generate_digest(person_id: int = Body(..., embed=True), db: Session = Depends(get_db)):
    try:
        return DigestService.generate_digest_for_person(db, person_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
