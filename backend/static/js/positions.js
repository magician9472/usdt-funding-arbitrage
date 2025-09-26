// /static/js/positions.js
(() => {
  const log = (...args) => console.log("[positions]", ...args);

  const ws = new WebSocket(`wss://${location.host}/ws/positions`);
  ws.onopen = () => log("✅ WebSocket 연결 성공");
  ws.onerror = (e) => console.error("WS error", e);
  ws.onclose = () => log("WS closed");

  ws.onmessage = (evt) => {
    log("FROM SERVER >>>", evt.data);
    try {
      const data = JSON.parse(evt.data);
      // _test 메시지
      if (data && data._test) return;

      // 포지션 없음 안내
      if (data && data.msg) {
        // 화면에 안내문 갱신
        return;
      }

      // payload 배열 렌더
      if (Array.isArray(data)) {
        // 예: data: [{ instId, holdSide, total, ... }, ...]
        // TODO: DOM 업데이트
      }
    } catch (e) {
      // 문자열이면 통과
    }
  };
})();
