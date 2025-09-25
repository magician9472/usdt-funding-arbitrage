const protocol = window.location.protocol === "https:" ? "wss://" : "ws://";
const ws = new WebSocket(protocol + window.location.host + "/ws/positions");

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  const list = document.getElementById("positions");
  list.innerHTML = "";

  data.forEach(pos => {
    const li = document.createElement("li");

    // 롱/숏 색상 구분
    li.style.color = pos.holdSide === "long" ? "green" : "red";

    // 포지션 정보 표시
    li.innerText = `${pos.instId} | ${pos.holdSide.toUpperCase()} | 수량: ${pos.total}`;

    // Close 버튼
    const btn = document.createElement("button");
    btn.innerText = "Close";
    btn.onclick = () => {
      fetch("/api/order", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          symbol: pos.instId,
          side: pos.holdSide === "long" ? "CLOSE_LONG" : "CLOSE_SHORT",
          usdAmount: 0
        })
      });
    };

    li.appendChild(btn);
    list.appendChild(li);
  });
};