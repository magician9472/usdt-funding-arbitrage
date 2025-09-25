import os
import asyncio
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from backend.routers import api, views, private_api, order_api, ws_router
from backend.update_task import update_loop
from backend.reset import reset_funding_table
import logging



# FastAPI 전체 로그 레벨 조정
logging.basicConfig(level=logging.WARNING)

# SQLAlchemy 관련
logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)

# HTTP 클라이언트 관련
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

app = FastAPI()

# 정적 파일
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")  # backend/static


if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# 라우터 등록
app.include_router(api.router)
app.include_router(views.router)
app.include_router(private_api.router, prefix="/api")
app.include_router(order_api.router, prefix="/api")
app.include_router(ws_router.router)

# 스타트업 이벤트
@app.on_event("startup")
async def startup_event():
    await reset_funding_table()
    asyncio.create_task(update_loop())



# 실행부 (Railway 호환)
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))  # Railway가 PORT 환경변수 제공
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)