function setupWS(url) {
  const protocol = window.location.protocol === "https:" ? "wss://" : "ws://";
  const ws = new WebSocket(protocol + window.location.host + url);

  ws.onopen = () => {
    document.getElementById("status-bitget").innerText = "✅ Bitget WebSocket 연결 성공";
    document.getElementById("status-binance").innerText = "✅ Binance WebSocket 연결 성공";
  };

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    const bitgetBody = document.getElementById("bitget-body");
    const binanceBody = document.getElementById("binance-body");
    bitgetBody.innerHTML = "";
    binanceBody.innerHTML = "";

    let positions = Array.isArray(data) ? data : [data];
    if (positions.length === 0 || positions[0].msg) {
      bitgetBody.innerHTML = `<tr><td colspan="9" style="text-align:center; color:gray;">데이터 없음</td></tr>`;
      binanceBody.innerHTML = `<tr><td colspan="9" style="text-align:center; color:gray;">데이터 없음</td></tr>`;
      return;
    }

    positions.forEach(pos => {
      const row = document.createElement("tr");
      const upl = parseFloat(pos.upl);
      const uplColor = isNaN(upl) ? "black" : (upl >= 0 ? "green" : "red");

      row.innerHTML = `
        <td>${pos.source}</td>
        <td>${pos.symbol}</td>
        <td class="${pos.side === "long" ? "long" : "short"}">${pos.side?.toUpperCase()}</td>
        <td>${pos.size}</td>
        <td style="color:${uplColor};">${upl}</td>
        <td>${pos.entryPrice}</td>
        <td>${pos.markPrice}</td>
        <td>${pos.liqPrice ?? ""}</td>
        <td>${pos.margin ?? pos.marginType ?? ""}</td>
      `;

      if (pos.source === "bitget") {
        bitgetBody.appendChild(row);
      } else if (pos.source === "binance") {
        binanceBody.appendChild(row);
      }
    });
  };

  ws.onerror = () => {
    document.getElementById("status-bitget").innerText = "❌ Bitget WebSocket 에러 발생";
    document.getElementById("status-binance").innerText = "❌ Binance WebSocket 에러 발생";
  };

  ws.onclose = () => {
    document.getElementById("status-bitget").innerText = "❌ Bitget WebSocket 연결 종료";
    document.getElementById("status-binance").innerText = "❌ Binance WebSocket 연결 종료";
  };
}

// 통합 WebSocket 연결
setupWS("/ws/positions");
