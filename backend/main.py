import os, asyncio, uvicorn, logging
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.routers import api, views, private_api, order_api, ws_router
from backend.update_task import update_loop
from pybitget.stream import SubscribeReq

logging.basicConfig(level=logging.INFO)

app = FastAPI()

# 정적 파일
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
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
    asyncio.create_task(update_loop())

    # Bitget 구독 시작
    ws_router.loop = asyncio.get_running_loop()
    channels = [SubscribeReq("umcbl", "positions", "default")]
    ws_router.bitget_ws.subscribe(channels, ws_router.on_message)
    print("🚀 Bitget positions 구독 시작")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)