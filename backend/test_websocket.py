import os
import json
import asyncio
import logging
from dotenv import load_dotenv
from pybitget.stream import BitgetWsClient, SubscribeReq, handel_error
from pybitget import logger

# 로그 설정
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("positions-sub")

# .env 파일 로드
load_dotenv()

# 환경변수에서 API 키 불러오기
API_KEY = os.getenv("BITGET_API_KEY")
API_SECRET = os.getenv("BITGET_API_SECRET")
API_PASS = os.getenv("BITGET_API_PASS")

if not all([API_KEY, API_SECRET, API_PASS]):
    raise RuntimeError("환경변수 BITGET_API_KEY, BITGET_API_SECRET, BITGET_API_PASS 를 설정하세요.")

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

async def main():
    # Bitget WebSocket 클라이언트 생성 (인증 포함)
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

    # 특정 심볼 포지션 구독 (예: BTCUSDT)
    channels = [SubscribeReq("umcbl", "positions", "default")]
    client.subscribe(channels, on_message)

    log.info("Bitget 포지션 채널 구독 시작...")

    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        log.info("종료합니다...")
        client.close()

if __name__ == "__main__":
    asyncio.run(main())