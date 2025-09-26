const protocol = window.location.protocol === "https:" ? "wss://" : "ws://";
const ws = new WebSocket(protocol + window.location.host + "/ws/positions");

ws.onopen = () => {
  document.getElementById("status").innerText = "✅ WebSocket 연결 성공";
};

ws.onmessage = (event) => {
  const body = document.getElementById("positions-body");
  body.innerHTML = "";

  let data = JSON.parse(event.data);

  if (data.msg) {
    body.innerHTML = `<tr><td colspan="8" style="text-align:center; color:gray;">${data.msg}</td></tr>`;
    return;
  }

  if (!Array.isArray(data)) data = [data];

  data.forEach(pos => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${pos.symbol}</td>
      <td class="${pos.side === "long" ? "long" : "short"}">${pos.side.toUpperCase()}</td>
      <td>${pos.size}</td>
      <td>${pos.entryPrice}</td>
      <td>${pos.markPrice}</td>
      <td>${pos.liqPrice}</td>
      <td>${pos.margin}</td>
      <td>${pos.pnl}</td>
    `;
    body.appendChild(row);
  });
};

ws.onerror = () => {
  document.getElementById("status").innerText = "❌ WebSocket 에러 발생";
};

ws.onclose = () => {
  document.getElementById("status").innerText = "❌ WebSocket 연결 종료";
};