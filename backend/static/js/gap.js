const statusEl = document.getElementById("status");
const tableEl = document.getElementById("fundingTable");
const bodyEl = document.getElementById("fundingBody");

// 추가: 업데이트 상태 표시용 요소
const lastUpdateEl = document.getElementById("lastUpdate");
const nextUpdateEl = document.getElementById("nextUpdate");

let fundingData = [];
let originalOrder = []; // 원래 순서 저장
let sortColumn = null;
let sortDirection = "none"; // "asc" | "desc" | "none"

// 헤더 요소
const thSymbol = document.getElementById("thSymbol");
const thBinance = document.getElementById("thBinance");
const thBitget = document.getElementById("thBitget");
const thGap = document.getElementById("thGap");

// 이벤트 바인딩
thSymbol.onclick = () => toggleSort("symbol", thSymbol);
thBinance.onclick = () => toggleSort("binance_rate", thBinance);
thBitget.onclick = () => toggleSort("bitget_rate", thBitget);
thGap.onclick = () => toggleSort("gap", thGap);

function clearIcons() {
  [thSymbol, thBinance, thBitget, thGap].forEach(th => {
    th.textContent = th.textContent.replace(/ ▲| ▼/g, "");
  });
}

function toggleSort(column, thEl) {
  if (sortColumn !== column) {
    sortColumn = column;
    sortDirection = "asc";
  } else {
    if (sortDirection === "asc") sortDirection = "desc";
    else if (sortDirection === "desc") sortDirection = "none";
    else sortDirection = "asc";
  }

  clearIcons();
  if (sortDirection === "asc") thEl.textContent += " ▲";
  else if (sortDirection === "desc") thEl.textContent += " ▼";

  renderTable();
}

// ✅ DB API에서 데이터 불러오기
async function fetchGapData() {
  const res = await fetch("/api/gap");
  if (!res.ok) return;
  const json = await res.json();

    fundingData = json.map(d => {
    const binanceRate = d.binance_rate * 100;
    const bitgetRate = d.bitget_rate * 100;

    return {
        symbol: d.symbol,
        binance_rate: binanceRate,
        bitget_rate: bitgetRate,
        gap: Math.abs(binanceRate - bitgetRate), // ✅ 절대값 GAP
        nextFundingTime: d.next_funding_time ? new Date(d.next_funding_time).getTime() : null
    };
    });


  if (originalOrder.length === 0) {
    originalOrder = fundingData.map(d => d.symbol);
  }

  renderTable();
  statusEl.style.display = "none";
  tableEl.style.display = "table";

  // ✅ 마지막 업데이트 시간 표시
  const now = new Date();
  if (lastUpdateEl) {
    lastUpdateEl.innerText = "마지막 업데이트: " + now.toLocaleTimeString();
  }
}


// 테이블 렌더링
function renderTable() {
  let rows = [...fundingData];

  if (sortDirection !== "none") {
    rows.sort((a, b) => {
      let aVal = a[sortColumn];
      let bVal = b[sortColumn];

      if (sortColumn === "symbol") {
        return sortDirection === "asc"
          ? aVal.localeCompare(bVal)
          : bVal.localeCompare(aVal);
      } else {
        return sortDirection === "asc" ? aVal - bVal : bVal - aVal;
      }
    });
  } else {
    // 원래 순서 복원
    rows.sort((a, b) => originalOrder.indexOf(a.symbol) - originalOrder.indexOf(b.symbol));
  }

  bodyEl.innerHTML = "";
  const now = Date.now();

  rows.forEach(row => {
    const tr = document.createElement("tr");

    const tdSymbol = document.createElement("td");
    tdSymbol.textContent = row.symbol;

    const tdBinance = document.createElement("td");
    tdBinance.textContent = row.binance_rate.toFixed(4);
    tdBinance.className = row.binance_rate >= 0 ? "positive" : "negative";

    const tdBitget = document.createElement("td");
    tdBitget.textContent = row.bitget_rate.toFixed(4);
    tdBitget.className = row.bitget_rate >= 0 ? "positive" : "negative";

    const tdGap = document.createElement("td");
    tdGap.textContent = row.gap.toFixed(4);
    tdGap.className = row.gap >= 0 ? "positive" : "negative";

    const tdTime = document.createElement("td");
    if (row.nextFundingTime) {
      let remainingMs = Math.max(row.nextFundingTime - now, 0);
      const hours = String(Math.floor(remainingMs / (1000 * 60 * 60))).padStart(2, '0');
      const minutes = String(Math.floor((remainingMs % (1000 * 60 * 60)) / (1000 * 60))).padStart(2, '0');
      const seconds = String(Math.floor((remainingMs % (1000 * 60)) / 1000)).padStart(2, '0');
      tdTime.textContent = `${hours}:${minutes}:${seconds}`;
    } else {
      tdTime.textContent = "-";
    }

    tr.appendChild(tdSymbol);
    tr.appendChild(tdBinance);
    tr.appendChild(tdBitget);
    tr.appendChild(tdGap);
    tr.appendChild(tdTime);
    bodyEl.appendChild(tr);
  });
}

// 최초 실행
fetchGapData();

// 정각 맞추기
function scheduleFetch() {
  const now = new Date();
  const msToNextMinute = (60 - now.getSeconds()) * 1000 - now.getMilliseconds();

  setTimeout(() => {
    fetchGapData(); // 정각에 실행
    setInterval(fetchGapData, 60000); // 이후 매 60초마다 실행
  }, msToNextMinute);

  // ✅ 다음 업데이트까지 남은 시간 카운트다운
  let countdown = Math.ceil(msToNextMinute / 1000);
  if (nextUpdateEl) {
    nextUpdateEl.innerText = `다음 업데이트까지: ${countdown}초`;
  }
  const countdownTimer = setInterval(() => {
    countdown--;
    if (countdown <= 0) {
      countdown = 60;
    }
    if (nextUpdateEl) {
      nextUpdateEl.innerText = `다음 업데이트까지: ${countdown}초`;
    }
  }, 1000);
}

scheduleFetch();

// 카운트다운은 매초 갱신 (펀딩 타이머용)
setInterval(renderTable, 1000);