import os, asyncio, json
from dotenv import load_dotenv
from binance import AsyncClient
import websockets

TARGET_SYMBOL = None   # 스냅샷에서 열린 포지션 심볼을 저장

positions, mark_prices = {}, {}

def normalize_position(pos: dict):
    """REST 포지션 데이터를 짧은 키로 맞춤"""
    return {
        "pa": pos.get("positionAmt"),
        "ep": pos.get("entryPrice"),
        "up": pos.get("unRealizedProfit"),
        "ps": pos.get("positionSide"),
        "mt": pos.get("marginType"),
        "l": pos.get("liquidationPrice"),
    }

async def show_positions():
    if not positions:
        print("현재 열린 포지션이 없습니다.\n")
        return
    print("="*80)
    for symbol, pos in positions.items():
        mark = mark_prices.get(symbol)
        entry = float(pos.get("ep", 0) or 0)
        size = float(pos.get("pa", 0) or 0)
        upl = pos.get("up")
        try:
            if mark and entry and size:
                m = float(mark)
                if size > 0:
                    upl = (m - entry) * size
                elif size < 0:
                    upl = (entry - m) * abs(size)
        except Exception:
            pass
        print(f"[{symbol}] side={pos.get('ps')} size={size} "
              f"entry={entry} mark={mark} upl={upl} "
              f"liq={pos.get('l')} marginType={pos.get('mt')}")
    print("="*80 + "\n")

async def snapshot_and_stream():
    global TARGET_SYMBOL

    load_dotenv()
    client = await AsyncClient.create(
        os.getenv("BINANCE_API_KEY"), os.getenv("BINANCE_API_SECRET")
    )

    # ✅ 스냅샷: 열린 포지션 하나만 선택
    all_positions = await client.futures_position_information()
    await client.close_connection()

    for pos in all_positions:
        if float(pos.get("positionAmt", 0) or 0) != 0:
            symbol = pos["symbol"]
            TARGET_SYMBOL = symbol
            positions[symbol] = normalize_position(pos)
            break

    await show_positions()

    if not TARGET_SYMBOL:
        print("열린 포지션이 없습니다. 종료합니다.")
        return

    # ✅ 실시간 markPrice 스트림 (전체 스트림에서 해당 심볼만 필터링)
    url = "wss://fstream.binance.com/ws/!markPrice@arr@1s"
    async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
        print(f"실시간 markPrice 수신 시작: {TARGET_SYMBOL}")
        while True:
            raw = await ws.recv()
            data = json.loads(raw)
            if isinstance(data, list):
                for item in data:
                    if item.get("e") == "markPriceUpdate" and item.get("s") == TARGET_SYMBOL:
                        mark_prices[item["s"]] = item["p"]
                        await show_positions()

if __name__ == "__main__":
    try:
        asyncio.run(snapshot_and_stream())
    except KeyboardInterrupt:
        print("종료합니다.")