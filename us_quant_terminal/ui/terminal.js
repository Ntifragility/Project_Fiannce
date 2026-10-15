const mainEl = document.getElementById('mainChart');
const oscEl = document.getElementById('oscChart');

const tvOptions = {
  layout: { background: { type: 'solid', color: '#131722' }, textColor: '#D1D4DC', attributionLogo: false },
  grid: { vertLines: { color: '#1E222D' }, horzLines: { color: '#1E222D' } },
  crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
  rightPriceScale: { borderColor: '#2A2E39', scaleMargins: { top: 0.08, bottom: 0.22 } },
  timeScale: { borderColor: '#2A2E39', timeVisible: true, rightOffset: 8 },
};

const mainChart = LightweightCharts.createChart(mainEl, tvOptions);
const oscChart = LightweightCharts.createChart(oscEl, {
  ...tvOptions,
  rightPriceScale: { borderColor: '#2A2E39', scaleMargins: { top: 0.15, bottom: 0.15 } },
});

const candleSeries = mainChart.addCandlestickSeries({
  upColor: '#26A69A', downColor: '#EF5350', borderVisible: false,
  wickUpColor: '#26A69A', wickDownColor: '#EF5350'
});
const volumeSeries = mainChart.addHistogramSeries({ priceFormat: { type: 'volume' }, priceScaleId: '' });
volumeSeries.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });

const maConfig = {
  SMA_50:   { color: '#2962FF', width: 2, style: 0, vis: true },
  SMA_200:  { color: '#FF6D00', width: 2, style: 0, vis: true },
  EMA_50:   { color: '#00BCD4', width: 2, style: 2, vis: true },
  EMA_200:  { color: '#FDD835', width: 2, style: 2, vis: true },
  VWMA_50:  { color: '#AB47BC', width: 2, style: 0, vis: false },
  VWMA_200: { color: '#7E57C2', width: 2, style: 2, vis: false },
  HMA_50:   { color: '#00E676', width: 2, style: 0, vis: true },
  HMA_200:  { color: '#1DE9B6', width: 2, style: 2, vis: false },
  KAMA_50:  { color: '#FF4081', width: 2, style: 0, vis: false },
};

const maSeriesMap = {};
Object.keys(maConfig).forEach(k => {
  const cfg = maConfig[k];
  maSeriesMap[k] = mainChart.addLineSeries({
    color: cfg.color, lineWidth: cfg.width, lineStyle: cfg.style,
    visible: cfg.vis, lastValueVisible: true, priceLineVisible: false
  });
});

const spreadSeries = oscChart.addHistogramSeries({ priceFormat: { type: 'price', precision: 2, minMove: 0.01 } });

mainChart.timeScale().subscribeVisibleLogicalRangeChange(r => { if (r) oscChart.timeScale().setVisibleLogicalRange(r); });
oscChart.timeScale().subscribeVisibleLogicalRangeChange(r => { if (r) mainChart.timeScale().setVisibleLogicalRange(r); });

let activeSymbolName = '';
let latestBarData = {};

function renderLegend(d) {
  if (!d) return;
  const cColor = d.close >= d.open ? '#26A69A' : '#EF5350';
  document.getElementById('tvLegend').innerHTML = `
    <div>
      <span class="tv-legend-title">${activeSymbolName}</span>
      <span>O <b style="color:${cColor}">${d.open?.toFixed(2) || '-'}</b></span> &nbsp;
      <span>H <b style="color:${cColor}">${d.high?.toFixed(2) || '-'}</b></span> &nbsp;
      <span>L <b style="color:${cColor}">${d.low?.toFixed(2) || '-'}</b></span> &nbsp;
      <span>C <b style="color:${cColor}">${d.close?.toFixed(2) || '-'}</b></span>
    </div>
    <div style="margin-top:2px;">
      <span style="color:#2962FF">SMA50: <b>${d.SMA_50 ?? '-'}</b></span> |
      <span style="color:#FF6D00">SMA200: <b>${d.SMA_200 ?? '-'}</b></span> |
      <span style="color:#00BCD4">EMA50: <b>${d.EMA_50 ?? '-'}</b></span> |
      <span style="color:#FDD835">EMA200: <b>${d.EMA_200 ?? '-'}</b></span>
    </div>
    <div>
      <span style="color:#00E676">HMA50: <b>${d.HMA_50 ?? '-'}</b></span> |
      <span style="color:#AB47BC">VWMA50: <b>${d.VWMA_50 ?? '-'}</b></span> |
      <span style="color:#FF4081">KAMA50: <b>${d.KAMA_50 ?? '-'}</b></span>
    </div>
  `;
}

mainChart.subscribeCrosshairMove(param => {
  if (!param.time || !param.seriesData.get(candleSeries)) {
    renderLegend(latestBarData);
    return;
  }
  const c = param.seriesData.get(candleSeries);
  const snap = { open: c.open, high: c.high, low: c.low, close: c.close };
  Object.keys(maSeriesMap).forEach(k => {
    snap[k] = param.seriesData.get(maSeriesMap[k])?.value;
  });
  renderLegend(snap);
});

function toggleSeries() {
  Object.keys(maSeriesMap).forEach(k => {
    const el = document.getElementById('t_' + k);
    if (el) maSeriesMap[k].applyOptions({ visible: el.checked });
  });
}

function resetZoom() {
  mainChart.timeScale().fitContent();
  mainChart.priceScale('right').applyOptions({ autoScale: true });
}

function onSectorChange() {
  document.getElementById('symSel').value = '';
  loadTerminal('');
}

// Set default date pickers on startup (Jan 1, 2026 to Today)
const todayIso = new Date().toISOString().split('T')[0];
document.getElementById('startDate').value = '2026-01-01';
document.getElementById('endDate').value = todayIso;

// Automatically reload when the user changes either date picker
document.getElementById('startDate').addEventListener('change', () => loadTerminal(''));
document.getElementById('endDate').addEventListener('change', () => loadTerminal(''));

async function loadTerminal(forcedSym) {
  const sector = document.getElementById('sectorSel').value || '';
  const active = forcedSym !== '' ? forcedSym : (document.getElementById('symSel').value || '');
  const tf = document.getElementById('tfSel').value || '1Day';
  const sig = document.getElementById('sigSel').value || 'EMA';
  const start = document.getElementById('startDate').value || '';
  const end = document.getElementById('endDate').value || '';
  const custom = document.getElementById('customInput').value || '';

  const res = await fetch(
    `/api/state?sector=${encodeURIComponent(sector)}&active=${encodeURIComponent(active)}` +
    `&tf=${tf}&sig=${sig}&start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}&custom=${encodeURIComponent(custom)}`
  );
  const data = await res.json();

  const secEl = document.getElementById('sectorSel');
  secEl.innerHTML = '';
  data.sectors.forEach(s => secEl.add(new Option(s, s)));
  secEl.value = data.active_sector;

  const symEl = document.getElementById('symSel');
  symEl.innerHTML = '';
  data.symbols.forEach(s => symEl.add(new Option(s, s)));
  symEl.value = data.active_sym;
  activeSymbolName = `${data.active_sym} · ${data.timeframe} (${start || 'Start'} to ${end || 'Now'})`;

  const tbody = document.querySelector('#wlTable tbody');
  tbody.innerHTML = '';
  data.scanner.forEach(r => {
    const tr = document.createElement('tr');
    if (r.ticker === data.active_sym) tr.className = 'active-row';
    tr.onclick = () => loadTerminal(r.ticker);
    const chgColor = r.chg >= 0 ? '#26A69A' : '#EF5350';
    const spColor = r.spread >= 0 ? '#26A69A' : '#EF5350';
    tr.innerHTML = `
      <td><b>${r.ticker}</b></td>
      <td>$${r.close.toFixed(2)}</td>
      <td style="color:${chgColor}">${r.chg >= 0 ? '+' : ''}${r.chg}%</td>
      <td style="color:${spColor}">${r.spread >= 0 ? '+' : ''}${r.spread}%</td>
      <td>${r.score}/4</td>
    `;
    tbody.appendChild(tr);
  });

  if (data.tv && data.tv.candles && data.tv.candles.length > 0) {
    candleSeries.setData(data.tv.candles);
    candleSeries.setMarkers(data.tv.markers || []);
    volumeSeries.setData(data.tv.volumes);
    spreadSeries.setData(data.tv.spread);

    const lastC = data.tv.candles[data.tv.candles.length - 1] || {};
    latestBarData = { open: lastC.open, high: lastC.high, low: lastC.low, close: lastC.close };

    Object.keys(maSeriesMap).forEach(k => {
      const arr = data.tv.ma_lines[k] || [];
      maSeriesMap[k].setData(arr);
      latestBarData[k] = arr.slice(-1)[0]?.value;
    });

    renderLegend(latestBarData);
    mainChart.timeScale().fitContent();
    oscChart.timeScale().fitContent();
  }

  const btBody = document.querySelector('#btTable tbody');
  btBody.innerHTML = '';
  (data.bt_comparison || []).forEach(b => {
    const tr = document.createElement('tr');
    const rColor = b['Total Strategy Return (%)'] >= 0 ? '#26A69A' : '#EF5350';
    tr.innerHTML = `
      <td><b>${b.ma_type}</b></td>
      <td style="color:${rColor};font-weight:700;">${b['Total Strategy Return (%)'] > 0 ? '+' : ''}${b['Total Strategy Return (%)']}%</td>
      <td>${b['Buy & Hold Return (%)']}%</td>
      <td>${b['Sharpe Ratio']}</td>
      <td style="color:#EF5350">${b['Max Drawdown (%)']}%</td>
      <td>${b.Trades}</td>
    `;
    btBody.appendChild(tr);
  });
}

window.addEventListener('resize', () => {
  mainChart.applyOptions({ width: mainEl.clientWidth, height: mainEl.clientHeight });
  oscChart.applyOptions({ width: oscEl.clientWidth, height: oscEl.clientHeight });
});

loadTerminal('');