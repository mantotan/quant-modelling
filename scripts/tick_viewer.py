"""Tick Viewer — Single-page Polymarket tick data visualizer.

Usage:
    python scripts/tick_viewer.py [--port 8501]

Opens a browser with an interactive chart showing bid/ask/P(UP) for
individual Polymarket candles, loaded from Hive-partitioned parquet files.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import polars as pl

try:
    import orjson

    def json_dumps(obj: object) -> bytes:
        return orjson.dumps(obj, option=orjson.OPT_SERIALIZE_NUMPY)
except ImportError:
    def json_dumps(obj: object) -> bytes:
        return json.dumps(obj, default=str).encode()

TICK_DIR = Path("data/raw/polymarket_ticks")
RESOLUTION_DIR = TICK_DIR / "resolutions"

# Allowed characters for query params (alphanumeric, dash, underscore)
_SAFE_PARAM = __import__("re").compile(r"^[A-Za-z0-9_\-]+$")


def _validate_param(name: str, value: str) -> bool:
    """Reject path-traversal attempts and other unsafe input."""
    return bool(_SAFE_PARAM.match(value))


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def scan_catalog() -> dict:
    """Return full asset/timeframe/date tree from filesystem."""
    assets = []
    for asset_dir in sorted(TICK_DIR.glob("asset=*")):
        asset_name = asset_dir.name.split("=", 1)[1]
        timeframes = []
        for tf_dir in sorted(asset_dir.glob("timeframe=*")):
            tf_name = tf_dir.name.split("=", 1)[1]
            dates = sorted(
                d.name.split("=", 1)[1]
                for d in tf_dir.glob("date=*")
                if any(d.glob("*.parquet"))
            )
            if dates:
                timeframes.append({"name": tf_name, "dates": dates})
        if timeframes:
            assets.append({"name": asset_name, "timeframes": timeframes})
    return {"assets": assets}


def load_resolutions(tf: str, date: str) -> dict[int, list[dict]]:
    """Load resolution JSONL into dict keyed by bar_id."""
    path = RESOLUTION_DIR / f"{tf}_{date}.jsonl"
    by_bar: dict[int, list[dict]] = {}
    if not path.exists():
        return by_bar
    with open(path) as f:
        for line in f:
            entry = json.loads(line)
            by_bar.setdefault(entry["bar_id"], []).append(entry)
    return by_bar


def list_candles(asset: str, tf: str, date: str) -> list[dict]:
    """List candle windows with resolution for a given asset/tf/date."""
    parquet_dir = TICK_DIR / f"asset={asset}" / f"timeframe={tf}" / f"date={date}"
    files = sorted(parquet_dir.glob("ticks_*.parquet"))
    if not files:
        return []

    # Read only the columns we need for candle listing
    df = pl.concat([
        pl.read_parquet(f, columns=["window_start", "window_end", "condition_id"])
        for f in files
    ])

    # Group by window to get unique candles + their condition_id + tick count
    candles_df = (
        df.group_by(["window_start", "window_end"])
        .agg([
            pl.col("condition_id")
            .filter(pl.col("condition_id") != "")
            .first()
            .alias("condition_id"),
            pl.len().alias("tick_count"),
        ])
        .sort("window_start")
    )

    rows = candles_df.to_dicts()

    # Build candle list with next-candle condition_id for resolution lookup
    candles = []
    for i, row in enumerate(rows):
        ws = row["window_start"]
        we = row["window_end"]
        bar_id = int(we.timestamp())
        cid = row["condition_id"] or ""
        # Next candle's condition_id (for resolution of THIS candle)
        next_cid = rows[i + 1]["condition_id"] if i + 1 < len(rows) else None
        next_cid = next_cid or ""

        candles.append({
            "window_start": ws.isoformat(),
            "window_end": we.isoformat(),
            "label": f"{ws.strftime('%H:%M')} → {we.strftime('%H:%M')}",
            "bar_id": bar_id,
            "condition_id": cid,
            "next_condition_id": next_cid,
            "tick_count": row["tick_count"],
        })

    # Resolve outcomes
    resolutions = load_resolutions(tf, date)
    for candle in candles:
        candle["resolution"] = _resolve_candle(
            resolutions, candle["bar_id"], candle["next_condition_id"]
        )

    return candles


def _resolve_candle(
    resolutions: dict[int, list[dict]], bar_id: int, next_cid: str
) -> str | None:
    """Determine UP/DN outcome for a candle.

    Uses next candle's condition_id to match against resolution entries
    at this candle's bar_id. Falls back to unanimous outcome if no
    condition_id match.
    """
    entries = resolutions.get(bar_id, [])
    if not entries:
        return None

    # Primary: match by next candle's condition_id
    if next_cid:
        for entry in entries:
            if entry["condition_id"] == next_cid:
                return entry["outcome"]

    # Fallback: if all entries agree on outcome
    outcomes = {e["outcome"] for e in entries}
    if len(outcomes) == 1:
        return outcomes.pop()

    return None


def load_ticks(asset: str, tf: str, date: str, window_start_iso: str) -> list[dict]:
    """Load all ticks for a specific candle window."""
    parquet_dir = TICK_DIR / f"asset={asset}" / f"timeframe={tf}" / f"date={date}"
    files = sorted(parquet_dir.glob("ticks_*.parquet"))
    if not files:
        return []

    # Parse the target window_start
    target_ws = pl.Series([window_start_iso]).str.to_datetime(
        "%Y-%m-%dT%H:%M:%S%.f%:z"
    )[0]

    cols = [
        "ts", "bid_up", "ask_up", "cal_prob", "raw_prob",
        "elapsed_pct", "is_inference", "spot_price",
        "window_start", "window_end",
    ]

    df = pl.concat([
        pl.read_parquet(f, columns=cols)
        for f in files
    ])

    # Filter to the target candle
    df = df.filter(pl.col("window_start") == target_ws).sort("ts")

    if df.is_empty():
        return []

    # Convert to list of dicts with epoch seconds for TradingView
    ticks = []
    for row in df.iter_rows(named=True):
        ticks.append({
            "time": row["ts"].timestamp(),
            "bid_up": _round(row["bid_up"]),
            "ask_up": _round(row["ask_up"]),
            "cal_prob": _round(row["cal_prob"]),
            "raw_prob": _round(row["raw_prob"]),
            "elapsed_pct": _round(row["elapsed_pct"]),
            "is_inference": row["is_inference"],
            "spot_price": _round(row["spot_price"]),
        })

    return ticks


def _round(v: float | None, n: int = 6) -> float | None:
    if v is None:
        return None
    return round(v, n)


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class TickViewerHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        params = parse_qs(parsed.query)

        if path == "/":
            self._serve_html()
        elif path == "/api/catalog":
            self._json_response(scan_catalog())
        elif path == "/api/candles":
            self._handle_candles(params)
        elif path == "/api/ticks":
            self._handle_ticks(params)
        else:
            self._error(404, "Not found")

    def _handle_candles(self, params: dict) -> None:
        asset = params.get("asset", [None])[0]
        tf = params.get("tf", [None])[0]
        date = params.get("date", [None])[0]
        if not all([asset, tf, date]):
            self._error(400, "Missing asset, tf, or date parameter")
            return
        params_to_check = [("asset", asset), ("tf", tf), ("date", date)]
        if not all(_validate_param(k, v) for k, v in params_to_check):
            self._error(400, "Invalid parameter value")
            return
        try:
            self._json_response(list_candles(asset, tf, date))
        except Exception as exc:
            self._error(500, f"Server error: {exc}")

    def _handle_ticks(self, params: dict) -> None:
        asset = params.get("asset", [None])[0]
        tf = params.get("tf", [None])[0]
        date = params.get("date", [None])[0]
        ws = params.get("ws", [None])[0]
        if not all([asset, tf, date, ws]):
            self._error(400, "Missing asset, tf, date, or ws parameter")
            return
        params_to_check = [("asset", asset), ("tf", tf), ("date", date)]
        if not all(_validate_param(k, v) for k, v in params_to_check):
            self._error(400, "Invalid parameter value")
            return
        try:
            ticks = load_ticks(asset, tf, date, ws)
            self._json_response({"ticks": ticks})
        except Exception as exc:
            self._error(500, f"Server error: {exc}")

    def _json_response(self, data: object, status: int = 200) -> None:
        body = json_dumps(data)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: int, msg: str) -> None:
        self._json_response({"error": msg}, status)

    def _serve_html(self) -> None:
        body = HTML_PAGE.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        # Suppress default request logging noise
        pass


# ---------------------------------------------------------------------------
# Inline HTML/JS/CSS
# ---------------------------------------------------------------------------

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tick Viewer</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600&family=Fira+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
<style>
  :root {
    --bg: #0F172A;
    --surface: #1E293B;
    --border: #334155;
    --text: #F8FAFC;
    --text-muted: #94A3B8;
    --green: #22C55E;
    --red: #EF4444;
    --gold: #F59E0B;
    --purple: #8B5CF6;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body { height: 100%; overflow: hidden; background: var(--bg); color: var(--text); font-family: 'Fira Sans', sans-serif; }

  .controls {
    display: flex; align-items: center; gap: 12px;
    padding: 10px 16px; background: var(--surface);
    border-bottom: 1px solid var(--border);
  }
  .controls select {
    background: var(--bg); color: var(--text); border: 1px solid var(--border);
    padding: 6px 10px; border-radius: 6px; font-family: 'Fira Code', monospace;
    font-size: 13px; cursor: pointer; outline: none;
    min-width: 80px;
  }
  .controls select:focus { border-color: var(--gold); }
  .controls select:disabled { opacity: 0.4; cursor: not-allowed; }

  .toolbar {
    display: flex; align-items: center; gap: 8px;
    padding: 6px 16px; background: var(--surface);
    border-bottom: 1px solid var(--border);
  }
  .toggle-btn {
    display: flex; align-items: center; gap: 6px;
    padding: 4px 12px; border-radius: 20px;
    background: none; border: 1.5px solid; font-size: 12px; font-weight: 500;
    font-family: 'Fira Sans', sans-serif;
    cursor: pointer; transition: all 0.15s ease;
    user-select: none;
  }
  .toggle-btn .dot {
    width: 8px; height: 8px; border-radius: 50%;
    transition: background 0.15s ease;
  }
  .toggle-btn.bid { border-color: var(--green); color: var(--green); }
  .toggle-btn.bid.active { background: var(--green); color: #000; }
  .toggle-btn.bid .dot { background: var(--green); }
  .toggle-btn.ask { border-color: var(--red); color: var(--red); }
  .toggle-btn.ask.active { background: var(--red); color: #fff; }
  .toggle-btn.ask .dot { background: var(--red); }
  .toggle-btn.prob { border-color: var(--gold); color: var(--gold); }
  .toggle-btn.prob.active { background: var(--gold); color: #000; }
  .toggle-btn.prob .dot { background: var(--gold); }

  .nav-btn {
    background: var(--bg); color: var(--text-muted); border: 1px solid var(--border);
    padding: 4px 10px; border-radius: 6px; cursor: pointer; font-size: 14px;
    transition: all 0.15s ease;
  }
  .nav-btn:hover { color: var(--text); border-color: var(--text-muted); }
  .nav-btn:disabled { opacity: 0.3; cursor: not-allowed; }

  .spacer { flex: 1; }

  .resolution-badge {
    padding: 4px 12px; border-radius: 20px; font-size: 12px;
    font-weight: 600; font-family: 'Fira Code', monospace;
    letter-spacing: 0.5px;
  }
  .resolution-badge.up { background: rgba(34,197,94,0.15); color: var(--green); border: 1px solid rgba(34,197,94,0.3); }
  .resolution-badge.dn { background: rgba(239,68,68,0.15); color: var(--red); border: 1px solid rgba(239,68,68,0.3); }
  .resolution-badge.na { background: rgba(148,163,184,0.1); color: var(--text-muted); border: 1px solid var(--border); }

  .tick-count {
    font-size: 11px; color: var(--text-muted); font-family: 'Fira Code', monospace;
  }

  #chart-container {
    width: 100%; flex: 1; position: relative;
  }
  .page { display: flex; flex-direction: column; height: 100vh; }

  .loading-overlay {
    position: absolute; inset: 0; display: flex; align-items: center;
    justify-content: center; background: rgba(15,23,42,0.7); z-index: 10;
  }
  .spinner {
    width: 32px; height: 32px; border: 3px solid var(--border);
    border-top-color: var(--gold); border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }

  .empty-state {
    position: absolute; inset: 0; display: flex; align-items: center;
    justify-content: center; color: var(--text-muted); font-size: 14px;
  }
</style>
</head>
<body>
<div class="page">
  <!-- Selectors row -->
  <div class="controls">
    <select id="sel-asset" disabled><option>Loading...</option></select>
    <select id="sel-tf" disabled></select>
    <select id="sel-date" disabled></select>
    <select id="sel-candle" disabled></select>
  </div>

  <!-- Toggles + nav row -->
  <div class="toolbar">
    <button type="button" class="toggle-btn bid active" data-series="bid" onclick="toggleSeries('bid')">
      <span class="dot"></span>Bid
    </button>
    <button type="button" class="toggle-btn ask active" data-series="ask" onclick="toggleSeries('ask')">
      <span class="dot"></span>Ask
    </button>
    <button type="button" class="toggle-btn prob active" data-series="prob" onclick="toggleSeries('prob')">
      <span class="dot"></span>P(UP)
    </button>
    <button type="button" class="nav-btn" id="btn-prev" onclick="navCandle(-1)" disabled>&#9664;</button>
    <button type="button" class="nav-btn" id="btn-next" onclick="navCandle(1)" disabled>&#9654;</button>
    <span class="tick-count" id="tick-count"></span>
    <span class="spacer"></span>
    <span class="resolution-badge na" id="resolution-badge">--</span>
  </div>

  <!-- Chart -->
  <div id="chart-container">
    <div class="empty-state" id="empty-state">Select a candle to view</div>
  </div>
</div>

<script>
// ---- State ----
let catalog = null;
let candles = [];
let chart = null;
let bidSeries = null, askSeries = null, probSeries = null;
let refLine = null;
let seriesVisible = { bid: true, ask: true, prob: true };
let abortCtrl = null;

// ---- DOM refs ----
const selAsset = document.getElementById('sel-asset');
const selTf = document.getElementById('sel-tf');
const selDate = document.getElementById('sel-date');
const selCandle = document.getElementById('sel-candle');
const btnPrev = document.getElementById('btn-prev');
const btnNext = document.getElementById('btn-next');
const tickCountEl = document.getElementById('tick-count');
const resBadge = document.getElementById('resolution-badge');
const chartContainer = document.getElementById('chart-container');
const emptyState = document.getElementById('empty-state');

// ---- Fetch helper ----
async function api(path, signal) {
  const resp = await fetch(path, { signal });
  if (!resp.ok) throw new Error(`API error: ${resp.status}`);
  return resp.json();
}

// ---- Init ----
async function init() {
  catalog = await api('/api/catalog');
  if (!catalog.assets.length) {
    emptyState.textContent = 'No tick data found';
    return;
  }
  populateSelect(selAsset, catalog.assets.map(a => a.name));
  selAsset.disabled = false;
  selAsset.addEventListener('change', onAssetChange);
  selTf.addEventListener('change', onTfChange);
  selDate.addEventListener('change', onDateChange);
  selCandle.addEventListener('change', onCandleChange);
  onAssetChange();
}

function populateSelect(sel, values, labels) {
  sel.innerHTML = '';
  values.forEach((v, i) => {
    const opt = document.createElement('option');
    opt.value = v;
    opt.textContent = labels ? labels[i] : v;
    sel.appendChild(opt);
  });
}

function onAssetChange() {
  const asset = catalog.assets.find(a => a.name === selAsset.value);
  if (!asset) return;
  populateSelect(selTf, asset.timeframes.map(t => t.name));
  selTf.disabled = false;
  onTfChange();
}

function onTfChange() {
  const asset = catalog.assets.find(a => a.name === selAsset.value);
  const tf = asset?.timeframes.find(t => t.name === selTf.value);
  if (!tf) return;
  populateSelect(selDate, tf.dates);
  selDate.disabled = false;
  onDateChange();
}

async function onDateChange() {
  selCandle.disabled = true;
  selCandle.innerHTML = '<option>Loading...</option>';
  try {
    candles = await api(`/api/candles?asset=${selAsset.value}&tf=${selTf.value}&date=${selDate.value}`);
    if (!candles.length) {
      selCandle.innerHTML = '<option>No candles</option>';
      return;
    }
    populateSelect(
      selCandle,
      candles.map(c => c.window_start),
      candles.map(c => `${c.label}  (${c.tick_count} ticks)`)
    );
    selCandle.disabled = false;
    updateNavButtons();
    onCandleChange();
  } catch (e) {
    selCandle.innerHTML = '<option>Error loading</option>';
  }
}

async function onCandleChange() {
  const ws = selCandle.value;
  const candle = candles.find(c => c.window_start === ws);
  if (!candle) return;

  // Update resolution badge
  updateResolution(candle.resolution);
  updateNavButtons();

  // Show loading
  emptyState.style.display = 'none';
  showLoading(true);

  // Cancel previous fetch
  if (abortCtrl) abortCtrl.abort();
  abortCtrl = new AbortController();

  try {
    const data = await api(
      `/api/ticks?asset=${selAsset.value}&tf=${selTf.value}&date=${selDate.value}&ws=${encodeURIComponent(ws)}`,
      abortCtrl.signal
    );
    tickCountEl.textContent = `${data.ticks.length} ticks`;
    renderChart(data.ticks);
  } catch (e) {
    if (e.name !== 'AbortError') {
      console.error('Failed to load ticks:', e);
      tickCountEl.textContent = 'Error';
    }
  } finally {
    showLoading(false);
  }
}

// ---- Chart ----
function initChart() {
  if (chart) return;
  chart = LightweightCharts.createChart(chartContainer, {
    layout: {
      background: { color: '#0F172A' },
      textColor: '#94A3B8',
      fontFamily: "'Fira Code', monospace",
      fontSize: 11,
    },
    grid: {
      vertLines: { color: 'rgba(51,65,85,0.3)' },
      horzLines: { color: 'rgba(51,65,85,0.3)' },
    },
    crosshair: {
      mode: LightweightCharts.CrosshairMode.Normal,
      vertLine: { color: 'rgba(248,250,252,0.2)', width: 1, style: LightweightCharts.LineStyle.Dashed },
      horzLine: { color: 'rgba(248,250,252,0.2)', width: 1, style: LightweightCharts.LineStyle.Dashed },
    },
    rightPriceScale: {
      borderColor: '#334155',
      scaleMargins: { top: 0.05, bottom: 0.05 },
    },
    timeScale: {
      borderColor: '#334155',
      timeVisible: true,
      secondsVisible: true,
      rightOffset: 5,
    },
    handleScroll: { vertTouchDrag: false },
  });

  bidSeries = chart.addLineSeries({
    color: '#22C55E', lineWidth: 1.5, title: 'Bid',
    priceLineVisible: false, lastValueVisible: true,
    crosshairMarkerRadius: 3,
  });
  askSeries = chart.addLineSeries({
    color: '#EF4444', lineWidth: 1.5, title: 'Ask',
    priceLineVisible: false, lastValueVisible: true,
    crosshairMarkerRadius: 3,
  });
  probSeries = chart.addLineSeries({
    color: '#F59E0B', lineWidth: 2, title: 'P(UP)',
    priceLineVisible: false, lastValueVisible: true,
    crosshairMarkerRadius: 3,
  });

  // Resize observer
  const ro = new ResizeObserver(entries => {
    for (const entry of entries) {
      const { width, height } = entry.contentRect;
      chart.resize(width, height);
    }
  });
  ro.observe(chartContainer);
}

function renderChart(ticks) {
  initChart();

  const bidData = [];
  const askData = [];
  const probData = [];
  const markers = [];

  for (const t of ticks) {
    const time = t.time;
    if (t.bid_up != null) bidData.push({ time, value: t.bid_up });
    if (t.ask_up != null) askData.push({ time, value: t.ask_up });
    if (t.cal_prob != null) probData.push({ time, value: t.cal_prob });
    if (t.is_inference) {
      markers.push({
        time,
        position: 'inBar',
        color: '#F59E0B',
        shape: 'circle',
        size: 1.5,
      });
    }
  }

  bidSeries.setData(bidData);
  askSeries.setData(askData);
  probSeries.setData(probData);
  probSeries.setMarkers(markers);

  // Apply visibility
  bidSeries.applyOptions({ visible: seriesVisible.bid });
  askSeries.applyOptions({ visible: seriesVisible.ask });
  probSeries.applyOptions({ visible: seriesVisible.prob });

  // 0.50 reference line
  if (refLine) {
    try { probSeries.removePriceLine(refLine); } catch(e) {}
  }
  refLine = probSeries.createPriceLine({
    price: 0.50,
    color: 'rgba(148,163,184,0.4)',
    lineWidth: 1,
    lineStyle: LightweightCharts.LineStyle.Dashed,
    axisLabelVisible: true,
    title: '',
  });

  chart.timeScale().fitContent();
}

// ---- Toggle ----
function toggleSeries(key) {
  seriesVisible[key] = !seriesVisible[key];
  const btn = document.querySelector(`.toggle-btn.${key}`);
  btn.classList.toggle('active', seriesVisible[key]);

  const seriesMap = { bid: bidSeries, ask: askSeries, prob: probSeries };
  if (seriesMap[key]) {
    seriesMap[key].applyOptions({ visible: seriesVisible[key] });
  }
}

// ---- Navigation ----
function navCandle(delta) {
  const idx = selCandle.selectedIndex + delta;
  if (idx < 0 || idx >= selCandle.options.length) return;
  selCandle.selectedIndex = idx;
  onCandleChange();
}

function updateNavButtons() {
  btnPrev.disabled = selCandle.selectedIndex <= 0;
  btnNext.disabled = selCandle.selectedIndex >= selCandle.options.length - 1;
}

document.addEventListener('keydown', (e) => {
  if (e.target.tagName === 'SELECT') return;
  if (e.key === 'ArrowLeft') { navCandle(-1); e.preventDefault(); }
  if (e.key === 'ArrowRight') { navCandle(1); e.preventDefault(); }
});

// ---- Resolution badge ----
function updateResolution(outcome) {
  resBadge.className = 'resolution-badge';
  if (outcome === 'UP') {
    resBadge.textContent = 'UP';
    resBadge.classList.add('up');
  } else if (outcome === 'DN') {
    resBadge.textContent = 'DN';
    resBadge.classList.add('dn');
  } else {
    resBadge.textContent = 'N/A';
    resBadge.classList.add('na');
  }
}

// ---- Loading ----
let loadingEl = null;
function showLoading(show) {
  if (show && !loadingEl) {
    loadingEl = document.createElement('div');
    loadingEl.className = 'loading-overlay';
    loadingEl.innerHTML = '<div class="spinner"></div>';
    chartContainer.appendChild(loadingEl);
  } else if (!show && loadingEl) {
    loadingEl.remove();
    loadingEl = null;
  }
}

// ---- Start ----
init();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Tick Viewer")
    parser.add_argument("--port", type=int, default=8501)
    args = parser.parse_args()

    if not TICK_DIR.exists():
        print(f"Error: {TICK_DIR} not found. Run from project root.")
        raise SystemExit(1)

    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), TickViewerHandler)
    except OSError as exc:
        print(f"Error: cannot bind to port {args.port}: {exc}")
        print(f"Try: python scripts/tick_viewer.py --port {args.port + 1}")
        raise SystemExit(1) from None
    url = f"http://127.0.0.1:{args.port}"
    print(f"Tick Viewer running at {url}")

    with contextlib.suppress(Exception):
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
