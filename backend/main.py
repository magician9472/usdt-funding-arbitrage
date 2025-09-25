import os
import asyncio
import uvicorn
import logging
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.routers import api, views, private_api, order_api, ws_router
from backend.update_task import update_loop
from pybitget.stream import BitgetWsClient, SubscribeReq, handel_error

# ws_router 안에서 가져올 것들
from backend.routers.ws_router import bitget_ws, on_message, SubscribeReq, log

# FastAPI 전체 로그 레벨 조정
logging.basicConfig(level=logging.WARNING)

# SQLAlchemy 관련
logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)

# HTTP 클라이언트 관련
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)


# 로그 설정
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("positions-sub")

# .env 로드
load_dotenv()
API_KEY = os.getenv("BITGET_API_KEY")
API_SECRET = os.getenv("BITGET_API_SECRET")
API_PASS = os.getenv("BITGET_API_PASS")

if not all([API_KEY, API_SECRET, API_PASS]):
    raise RuntimeError("환경변수 BITGET_API_KEY, BITGET_API_SECRET, BITGET_API_PASS 를 설정하세요.")




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

# 메시지 콜백
def on_message(message: str):
    try:
        log.info(f"RAW >>> {message}")
        data = json.loads(message)

        if data.get("arg", {}).get("channel") == "positions":
            payload = data.get("data", [])
            if not payload:
                log.info("포지션 데이터 없음 (현재 열린 포지션이 없습니다).")
                return

            for pos in payload:
                inst_id = pos.get("instId")
                side = pos.get("holdSide")
                total = pos.get("total")
                log.info(f"[{inst_id}] {side} | 수량={total}")
    except Exception as e:
        log.error(f"메시지 파싱 오류: {e}")

# WebSocket 실행 함수
async def run_ws():
    client = (
        BitgetWsClient(
            api_key=API_KEY,
            api_secret=API_SECRET,
            passphrase=API_PASS,
            verbose=True
        )
        .error_listener(handel_error)
        .build()
    )
    channels = [SubscribeReq("umcbl", "positions", "default")]
    client.subscribe(channels, on_message)

    log.info("Bitget 포지션 채널 구독 시작...")

    while True:
        await asyncio.sleep(1)


# 스타트업 이벤트
@app.on_event("startup")
async def startup_event():
    # 백그라운드 업데이트 루프
    asyncio.create_task(update_loop())

    asyncio.create_task(run_ws())

@app.get("/")
async def root():
    return {"message": "Bitget Position Listener Running on Railway!"}


# 실행부 (Railway 호환)
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))  # Railway가 PORT 환경변수 제공
    uvicorn.run("main:app", host="0.0.0.0", port=port)