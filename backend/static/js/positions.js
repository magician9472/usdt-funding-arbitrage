const protocol = window.location.protocol === "https:" ? "wss://" : "ws://";
const ws = new WebSocket(protocol + window.location.host + "/ws/positions");

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  const list = document.getElementById("positions");
  list.innerHTML = "";
  data.forEach(pos => {
    const li = document.createElement("li");
    li.innerText = pos.instId + " " + pos.holdSide + " " + pos.total;

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