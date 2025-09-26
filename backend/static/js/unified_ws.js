(() => {
  const WS_URL = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/positions/all`;
  const tbody = document.getElementById("positions-body");
  const statusEl = document.getElementById("connection-status");

  let ws;
  let reconnectDelay = 1000; // 1s → 최대 10s

  function setStatus(type, text) {
    statusEl.className = "badge";
    if (type === "ok") statusEl.classList.add("badge-success");
    else if (type === "warn") statusEl.classList.add("badge-warning");
    else statusEl.classList.add("badge-danger");
    statusEl.textContent = text;
  }

  function fmtNum(n, opts = {}) {
    if (n === null || n === undefined || n === "") return "";
    const num = typeof n === "number" ? n : parseFloat(n);
    if (!isFinite(num)) return "";
    const { decimals = 6, trim = true } = opts;
    let s = num.toFixed(decimals);
    if (trim) s = s.replace(/\.?0+$/, "");
    return s;
  }

  function renderRows(rows) {
    if (!Array.isArray(rows) || rows.length === 0) {
      tbody.innerHTML = `<tr class="placeholder"><td colspan="9">현재 열린 포지션이 없습니다.</td></tr>`;
      return;
    }

    const html = rows.map(row => {
      const exClass = row.exchange === "binance" ? "exchange-binance" : "exchange-bitget";
      const sideClass = row.side === "LONG" ? "side-long" : row.side === "SHORT" ? "side-short" : "muted";
      const pnlClass = (row.upl || 0) >= 0 ? "pnl-pos" : "pnl-neg";

      return `
        <tr>
          <td><span class="exchange-badge ${exClass}">${row.exchange}</span></td>
          <td>${row.symbol ?? ""}</td>
          <td class="${sideClass}">${row.side ?? ""}</td>
          <td>${fmtNum(row.size, {decimals: 6})}</td>
          <td class="${pnlClass}">${fmtNum(row.upl, {decimals: 6})}</td>
          <td>${fmtNum(row.entryPrice, {decimals: 8})}</td>
          <td>${fmtNum(row.markPrice, {decimals: 8})}</td>
          <td>${fmtNum(row.liqPrice, {decimals: 8})}</td>
          <td>${fmtNum(row.margin, {decimals: 6})}</td>
        </tr>
      `;
    }).join("");

    tbody.innerHTML = html;
  }

  function connect() {
    setStatus("warn", "연결 중...");
    ws = new WebSocket(WS_URL);

    ws.onopen = () => {
      setStatus("ok", "연결됨");
      reconnectDelay = 1000;
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        renderRows(data);
      } catch (e) {
        console.error("메시지 파싱 오류:", e);
      }
    };

    ws.onclose = () => {
      setStatus("warn", "연결 끊김, 재시도 중...");
      scheduleReconnect();
    };

    ws.onerror = (err) => {
      console.error("WS 에러:", err);
      setStatus("danger", "에러 발생");
      ws.close();
    };
  }

  function scheduleReconnect() {
    setTimeout(() => {
      reconnectDelay = Math.min(reconnectDelay * 2, 10000);
      connect();
    }, reconnectDelay);
  }

  // 초기 연결
  connect();
})();