async function placeOrder(action) {
  const exchange = document.getElementById("exchange").value;
  const symbol = document.getElementById("symbol").value.trim();
  const usdAmount = parseFloat(document.getElementById("usdAmount").value);
  const priceVal = document.getElementById("price").value.trim();
  const leverage = parseInt(document.getElementById("leverage").value);
  const marginMode = document.getElementById("marginMode").value;
  const stopLossVal = document.getElementById("stopLoss").value.trim();

  if (!symbol || !usdAmount || usdAmount <= 0) {
    return showResult({status: "error", message: "심볼과 금액(USDT)을 올바르게 입력하세요."});
  }

  let sideParam = action;

  if (exchange === "bitget") {
    if (action === "BUY") sideParam = "open_long";
    else if (action === "SELL") sideParam = "open_short";
    else if (action === "CLOSE_LONG") sideParam = "close_long";
    else if (action === "CLOSE_SHORT") sideParam = "close_short";
  }

  const payload = {
    symbol,
    side: sideParam,
    usdAmount,
    price: priceVal ? parseFloat(priceVal) : null,
    leverage,
    marginMode,
    stopLoss: stopLossVal ? parseFloat(stopLossVal) : null
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