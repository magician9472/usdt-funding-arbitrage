import os, asyncio, uvicorn, logging
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from backend.routers import api, views, private_api, order_api, ws_router
from backend.update_task import update_loop
from pybitget.stream import SubscribeReq

logging.basicConfig(level=logging.INFO)

@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_running_loop()
    ws_router.loop = loop

    # 처음에는 positions 채널만 구독
    ws_router.bitget_ws.subscribe(
        [SubscribeReq("umcbl", "positions", "default")],
        ws_router.on_message
    )
    print("🚀 Bitget positions 구독 시작")

    asyncio.create_task(update_loop())
    yield
    print("🛑 앱 종료, Bitget 연결 닫기")
    ws_router.bitget_ws.close()

app = FastAPI(lifespan=lifespan)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

app.include_router(api.router)
app.include_router(views.router)
app.include_router(private_api.router, prefix="/api")
app.include_router(order_api.router, prefix="/api")
app.include_router(ws_router.router)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)