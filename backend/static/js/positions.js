const protocol = window.location.protocol === "https:" ? "wss://" : "ws://";
const ws = new WebSocket(protocol + window.location.host + "/ws/positions");

ws.onopen = () => {
  console.log("✅ WebSocket 연결 성공");
  const li = document.createElement("li");
  li.innerText = "✅ WebSocket 연결 성공";
  li.style.color = "blue";
  document.getElementById("positions").appendChild(li);
};

ws.onmessage = (event) => {
  let data = JSON.parse(event.data);
  const list = document.getElementById("positions");
  list.innerHTML = "";

  if (data.msg) {
    const li = document.createElement("li");
    li.innerText = data.msg;
    li.style.color = "gray";
    list.appendChild(li);
    return;
  }

  if (!Array.isArray(data)) data = [data];

  data.forEach(pos => {
    const li = document.createElement("li");
    li.style.color = pos.holdSide === "long" ? "green" : "red";
    li.innerText = `${pos.instId} | ${pos.holdSide?.toUpperCase()} | 수량: ${pos.total}`;
    list.appendChild(li);
  });
};