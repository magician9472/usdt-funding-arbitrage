import asyncio
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from routers import api, views, private_api, order_api




from update_task import update_loop

app = FastAPI()

# 정적 파일
app.mount("/static", StaticFiles(directory="static"), name="static")

# 라우터 등록
app.include_router(api.router)
app.include_router(views.router)
app.include_router(private_api.router, prefix="/api")
app.include_router(order_api.router, prefix="/api")



# 스타트업 이벤트
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(update_loop())