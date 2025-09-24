async function fetchBitget() {
  const res = await fetch("/api/bitget/latest");
  if (!res.ok) return;
  const data = await res.json();

  const tbody = document.getElementById("fundingBody");
  tbody.innerHTML = "";
  const now = Date.now();

  data.forEach(row => {
    const tr = document.createElement("tr");

    const tdSymbol = document.createElement("td");
    tdSymbol.textContent = row.symbol;

    const tdRate = document.createElement("td");
    tdRate.textContent = (row.funding_rate * 100).toFixed(4);

    const tdTime = document.createElement("td");
    if (row.next_funding_time) {
      const nft = new Date(row.next_funding_time).getTime();
      let remainingMs = Math.max(nft - now, 0);
      const hours = String(Math.floor(remainingMs / (1000 * 60 * 60))).padStart(2, '0');
      const minutes = String(Math.floor((remainingMs % (1000 * 60 * 60)) / (1000 * 60))).padStart(2, '0');
      const seconds = String(Math.floor((remainingMs % (1000 * 60)) / 1000)).padStart(2, '0');
      tdTime.textContent = `${hours}:${minutes}:${seconds}`;
    } else {
      tdTime.textContent = "-";
    }

    tr.appendChild(tdSymbol);
    tr.appendChild(tdRate);
    tr.appendChild(tdTime);
    tbody.appendChild(tr);
  });

  document.getElementById("status").style.display = "none";
  document.getElementById("fundingTable").style.display = "table";
}

fetchBitget();
setInterval(fetchBitget, 30000);