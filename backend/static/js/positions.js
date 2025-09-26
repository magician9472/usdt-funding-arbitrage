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
  console.log("FROM SERVER >>>", event.data);

  let data;
  try {
    data = JSON.parse(event.data);
  } catch (e) {
    console.error("❌ JSON 파싱 오류:", e);
    return;
  }

  const list = document.getElementById("positions");
  list.innerHTML = "";

  // 포지션 없음 메시지 처리
  if (data.msg) {
    const li = document.createElement("li");
    li.innerText = data.msg;
    li.style.color = "gray";
    list.appendChild(li);
    return;
  }

  // 배열/단일 객체 모두 대응
  if (!Array.isArray(data)) {
    data = [data];
  }

  data.forEach(pos => {
    const li = document.createElement("li");
    li.style.color = pos.holdSide === "long" ? "green" : "red";
    li.innerText = `${pos.instId} | ${pos.holdSide?.toUpperCase()} | 수량: ${pos.total}`;
    list.appendChild(li);
  });
};

ws.onerror = (err) => {
  console.error("❌ WebSocket 에러:", err);
};

ws.onclose = () => {
  console.log("❌ WebSocket 연결 종료");
};
