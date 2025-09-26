import os
from binance import ThreadedWebsocketManager, Client
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")

def handle_user_data(msg):
    """
    Binance User Data Stream 이벤트 핸들러
    포지션 정보는 ACCOUNT_UPDATE 이벤트에서 확인 가능
    """
    print("📩 이벤트:", msg)

    if msg.get("e") == "ACCOUNT_UPDATE":
        positions = msg["a"]["P"]
        for pos in positions:
            print(
                f"심볼: {pos['s']}, "
                f"수량: {pos['pa']}, "
                f"진입가: {pos['ep']}, "
                f"미실현손익: {pos['up']}, "
                f"방향: {pos['ps']}"
            )

def main():
    # Futures 클라이언트 생성
    client = Client(api_key=API_KEY, api_secret=API_SECRET)

    # WebSocket Manager 시작
    twm = ThreadedWebsocketManager(api_key=API_KEY, api_secret=API_SECRET)
    twm.start()

    # Futures User Data Stream 시작
    # listenKey 발급 및 keepalive는 라이브러리가 자동 처리
    twm.start_futures_user_socket(callback=handle_user_data)

    # 메인 스레드 유지
    twm.join()

if __name__ == "__main__":
    main()