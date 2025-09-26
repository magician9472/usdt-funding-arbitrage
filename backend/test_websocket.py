import asyncio
import json
import logging
from pybitget.stream import BitgetWsClient, handel_error, SubscribeReq

# 로그 설정
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("bitget-multi-ticker")

def on_message(message: str):
    try:
        data = json.loads(message)
        arg = data.get("arg", {})
        if arg.get("channel") == "ticker":
            for t in data.get("data", []):
                inst_id = t.get("instId")
                last = t.get("last")
                mark = t.get("markPrice")
                log.info(f"[{inst_id}] last={last} | markPrice={mark}")
    except Exception as e:
        log.error(f"메시지 파싱 오류: {e}")

async def main():
    # 퍼블릭 채널은 인증 필요 없음
    client = BitgetWsClient(verbose=True).error_listener(handel_error).build()

    # BTCUSDT, ETHUSDT 두 개 티커 구독
    channels = [
        SubscribeReq("mc", "ticker", "BTCUSDT")
    ]
    client.subscribe(channels, on_message)

    log.info("🚀 Bitget BTCUSDT + ETHUSDT ticker 구독 시작")
    while True:
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())