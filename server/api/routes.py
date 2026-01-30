from fastapi import APIRouter

router = APIRouter()


@router.get("/ping")
async def ping() -> dict:
    return {"status": "ok"}


@router.get("/version")
async def version() -> dict:
    return {"service": "inarbit", "version": "3.0.0"}
