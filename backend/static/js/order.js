async function placeOrder(side) {
  const exchange = document.getElementById("exchange").value;
  const symbol = document.getElementById("symbol").value.trim();
  const usdAmount = parseFloat(document.getElementById("usdAmount").value);
  const price = document.getElementById("price").value.trim();
  const leverage = parseInt(document.getElementById("leverage").value);
  const marginMode = document.getElementById("marginMode").value;
  const stopLoss = document.getElementById("stopLoss").value.trim();

  if (!symbol || !usdAmount || usdAmount <= 0) {
    return showResult({status: "error", message: "심볼과 금액(USDT)을 올바르게 입력하세요."});
  }

  let sideParam = side;
  if (exchange === "bitget") {
    sideParam = (side === "BUY") ? "open_long" : "open_short";
  }

  const payload = {
    symbol,
    side: sideParam,
    usdAmount,
    price: price || null,
    leverage,
    marginMode,
    stopLoss: stopLoss || null
  };

  try {
    const res = await fetch(`/api/${exchange}/order`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    showResult(data);
  } catch (err) {
    showResult({status: "error", message: String(err)});
  }
}

function showResult(data) {
  document.getElementById("result").textContent = JSON.stringify(data, null, 2);
}