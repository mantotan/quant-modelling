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
PAPER_DIR = Path("data/dutch_paper")
BACKTEST_DIR = Path("data/dutch_backtest")

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
        "ts", "bid_up", "bid_dn", "cal_prob", "raw_prob",
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
        bid_up = _round(row["bid_up"])
        bid_dn = _round(row["bid_dn"])
        cal_prob = _round(row["cal_prob"])
        ticks.append({
            "time": row["ts"].timestamp(),
            "bid_up": bid_up,
            "bid_dn": bid_dn,
            "cal_prob": cal_prob,
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


def load_events(
    asset: str, tf: str, date: str, bar_id: int,
) -> list[dict]:
    """Load Dutch engine events for a specific candle from paper/backtest logs."""
    key = f"{asset}_{tf}"
    events: list[dict] = []
    for base_dir in [PAPER_DIR, BACKTEST_DIR]:
        log_dir = base_dir / key
        log_file = log_dir / f"events_{date}.jsonl"
        if not log_file.exists():
            continue
        with open(log_file) as f:
            for line in f:
                entry = json.loads(line)
                if entry.get("bar_id") == bar_id:
                    events.append(entry)
        if events:
            break  # prefer paper over backtest
    return events


def load_bar_summary(
    asset: str, tf: str, date: str, bar_id: int,
) -> dict | None:
    """Load bar summary (PnL, orders, stats) for a specific candle."""
    key = f"{asset}_{tf}"
    for base_dir in [PAPER_DIR, BACKTEST_DIR]:
        log_dir = base_dir / key
        log_file = log_dir / f"bars_{date}.jsonl"
        if not log_file.exists():
            continue
        with open(log_file) as f:
            for line in f:
                entry = json.loads(line)
                if entry.get("bar_id") == bar_id:
                    return entry
    return None


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
        bar_id_str = params.get("bar_id", [None])[0]
        bar_id = int(bar_id_str) if bar_id_str else None
        try:
            ticks = load_ticks(asset, tf, date, ws)
            events = load_events(asset, tf, date, bar_id) if bar_id else []
            bar_summary = load_bar_summary(asset, tf, date, bar_id) if bar_id else None
            self._json_response({
                "ticks": ticks,
                "events": events,
                "bar_summary": bar_summary,
            })
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
  :root { --bg:#0F172A; --surface:#1E293B; --border:#334155; --text:#F8FAFC; --muted:#94A3B8; --green:#22C55E; --red:#EF4444; --gold:#F59E0B; --purple:#8B5CF6; --cyan:#06B6D4; }
  * { margin:0; padding:0; box-sizing:border-box; }
  html,body { height:100%; overflow:hidden; background:var(--bg); color:var(--text); font-family:'Fira Sans',sans-serif; }
  .page { display:flex; flex-direction:column; height:100vh; }
  .controls { display:flex; align-items:center; gap:12px; padding:10px 16px; background:var(--surface); border-bottom:1px solid var(--border); }
  .controls select { background:var(--bg); color:var(--text); border:1px solid var(--border); padding:6px 10px; border-radius:6px; font-family:'Fira Code',monospace; font-size:13px; cursor:pointer; outline:none; min-width:80px; }
  .controls select:focus { border-color:var(--gold); }
  .controls select:disabled { opacity:0.4; cursor:not-allowed; }
  .toolbar { display:flex; align-items:center; gap:8px; padding:6px 16px; background:var(--surface); border-bottom:1px solid var(--border); flex-wrap:wrap; }
  .toggle-btn { display:flex; align-items:center; gap:6px; padding:4px 12px; border-radius:20px; background:none; border:1.5px solid; font-size:12px; font-weight:500; font-family:'Fira Sans',sans-serif; cursor:pointer; transition:all .15s ease; user-select:none; }
  .toggle-btn .dot { width:8px; height:8px; border-radius:50%; }
  .toggle-btn.bid-up { border-color:var(--green); color:var(--green); } .toggle-btn.bid-up.active { background:var(--green); color:#000; } .toggle-btn.bid-up .dot { background:var(--green); }
  .toggle-btn.bid-dn { border-color:var(--red); color:var(--red); } .toggle-btn.bid-dn.active { background:var(--red); color:#fff; } .toggle-btn.bid-dn .dot { background:var(--red); }
  .toggle-btn.prob { border-color:var(--gold); color:var(--gold); } .toggle-btn.prob.active { background:var(--gold); color:#000; } .toggle-btn.prob .dot { background:var(--gold); }
  .nav-btn { background:var(--bg); color:var(--muted); border:1px solid var(--border); padding:4px 10px; border-radius:6px; cursor:pointer; font-size:14px; transition:all .15s ease; }
  .nav-btn:hover { color:var(--text); border-color:var(--muted); } .nav-btn:disabled { opacity:0.3; cursor:not-allowed; }
  .spacer { flex:1; }
  .info-pill { font-size:11px; font-family:'Fira Code',monospace; padding:3px 10px; border-radius:12px; }
  .pnl-badge { border:1px solid var(--border); }
  .pnl-badge.pos { color:var(--green); border-color:rgba(34,197,94,0.3); background:rgba(34,197,94,0.1); }
  .pnl-badge.neg { color:var(--red); border-color:rgba(239,68,68,0.3); background:rgba(239,68,68,0.1); }
  .pnl-badge.na { color:var(--muted); }
  .resolution-badge { padding:4px 12px; border-radius:20px; font-size:12px; font-weight:600; font-family:'Fira Code',monospace; }
  .resolution-badge.up { background:rgba(34,197,94,0.15); color:var(--green); border:1px solid rgba(34,197,94,0.3); }
  .resolution-badge.dn { background:rgba(239,68,68,0.15); color:var(--red); border:1px solid rgba(239,68,68,0.3); }
  .resolution-badge.na { background:rgba(148,163,184,0.1); color:var(--muted); border:1px solid var(--border); }
  .tick-count { font-size:11px; color:var(--muted); font-family:'Fira Code',monospace; }
  #chart-container { width:100%; flex:1; position:relative; }
  .loading-overlay { position:absolute; inset:0; display:flex; align-items:center; justify-content:center; background:rgba(15,23,42,0.7); z-index:10; }
  .spinner { width:32px; height:32px; border:3px solid var(--border); border-top-color:var(--gold); border-radius:50%; animation:spin .8s linear infinite; }
  @keyframes spin { to { transform:rotate(360deg); } }
  .empty-state { position:absolute; inset:0; display:flex; align-items:center; justify-content:center; color:var(--muted); font-size:14px; }
</style>
</head>
<body>
<div class="page">
  <div class="controls">
    <select id="sel-asset" disabled><option>Loading...</option></select>
    <select id="sel-tf" disabled></select>
    <select id="sel-date" disabled></select>
    <select id="sel-candle" disabled></select>
  </div>
  <div class="toolbar">
    <button type="button" class="toggle-btn bid-up active" onclick="toggleSeries('bid_up')"><span class="dot"></span>Bid UP</button>
    <button type="button" class="toggle-btn bid-dn active" onclick="toggleSeries('bid_dn')"><span class="dot"></span>Bid DN</button>
    <button type="button" class="toggle-btn prob active" onclick="toggleSeries('prob')"><span class="dot"></span>P(UP)</button>
    <button type="button" class="nav-btn" id="btn-prev" onclick="navCandle(-1)" disabled>&#9664;</button>
    <button type="button" class="nav-btn" id="btn-next" onclick="navCandle(1)" disabled>&#9654;</button>
    <span class="tick-count" id="tick-count"></span>
    <span class="spacer"></span>
    <span class="info-pill pnl-badge na" id="pnl-badge">PnL --</span>
    <span class="resolution-badge na" id="resolution-badge">--</span>
  </div>
  <div id="chart-container">
    <div class="empty-state" id="empty-state">Select a candle to view</div>
  </div>
</div>
<script>
let catalog=null, candles=[], chart=null;
let bidUpSeries=null, bidDnSeries=null, probSeries=null, refLine=null;
let currentTicks=[], currentEvents=[], eventMarkerData=[], toolTip=null;
let seriesVisible={bid_up:true,bid_dn:true,prob:true}, abortCtrl=null;

const $=id=>document.getElementById(id);
const selAsset=$('sel-asset'), selTf=$('sel-tf'), selDate=$('sel-date'), selCandle=$('sel-candle');
const btnPrev=$('btn-prev'), btnNext=$('btn-next'), tickCountEl=$('tick-count');
const resBadge=$('resolution-badge'), pnlBadge=$('pnl-badge');
const chartContainer=$('chart-container'), emptyState=$('empty-state');

async function api(path,signal){const r=await fetch(path,{signal});if(!r.ok)throw new Error(r.status);return r.json();}
function populateSelect(sel,values,labels){sel.innerHTML='';values.forEach((v,i)=>{const o=document.createElement('option');o.value=v;o.textContent=labels?labels[i]:v;sel.appendChild(o);});}

async function init(){
  catalog=await api('/api/catalog');
  if(!catalog.assets.length){emptyState.textContent='No tick data found';return;}
  populateSelect(selAsset,catalog.assets.map(a=>a.name));
  selAsset.disabled=false;
  selAsset.addEventListener('change',onAssetChange);
  selTf.addEventListener('change',onTfChange);
  selDate.addEventListener('change',onDateChange);
  selCandle.addEventListener('change',onCandleChange);
  onAssetChange();
}
function onAssetChange(){const a=catalog.assets.find(a=>a.name===selAsset.value);if(!a)return;populateSelect(selTf,a.timeframes.map(t=>t.name));selTf.disabled=false;onTfChange();}
function onTfChange(){const a=catalog.assets.find(a=>a.name===selAsset.value);const tf=a?.timeframes.find(t=>t.name===selTf.value);if(!tf)return;populateSelect(selDate,tf.dates);selDate.disabled=false;onDateChange();}
async function onDateChange(){
  selCandle.disabled=true;selCandle.innerHTML='<option>Loading...</option>';
  try{
    candles=await api(`/api/candles?asset=${selAsset.value}&tf=${selTf.value}&date=${selDate.value}`);
    if(!candles.length){selCandle.innerHTML='<option>No candles</option>';return;}
    populateSelect(selCandle,candles.map(c=>c.window_start),candles.map(c=>`${c.label}  (${c.tick_count} ticks)`));
    selCandle.disabled=false;updateNavButtons();onCandleChange();
  }catch(e){selCandle.innerHTML='<option>Error</option>';}
}
async function onCandleChange(){
  const ws=selCandle.value,candle=candles.find(c=>c.window_start===ws);
  if(!candle)return;
  updateResolution(candle.resolution);updateNavButtons();
  emptyState.style.display='none';showLoading(true);
  if(abortCtrl)abortCtrl.abort();abortCtrl=new AbortController();
  try{
    const data=await api(`/api/ticks?asset=${selAsset.value}&tf=${selTf.value}&date=${selDate.value}&ws=${encodeURIComponent(ws)}&bar_id=${candle.bar_id}`,abortCtrl.signal);
    const evts=data.events||[];
    tickCountEl.textContent=`${data.ticks.length} ticks`+(evts.length?` | ${evts.length} events`:'');
    currentTicks=data.ticks;currentEvents=evts;
    updatePnl(data.bar_summary);
    renderChart(data.ticks,evts);
  }catch(e){if(e.name!=='AbortError'){console.error(e);tickCountEl.textContent='Error';}}
  finally{showLoading(false);}
}

// ---- PnL badge ----
function updatePnl(summary){
  if(!summary||!summary.pnl){pnlBadge.textContent='PnL --';pnlBadge.className='info-pill pnl-badge na';return;}
  const p=summary.pnl;
  const profit=p.profit!=null?p.profit:0;
  const roi=p.roi_pct!=null?p.roi_pct:0;
  const sign=profit>=0?'+':'';
  pnlBadge.textContent=`PnL ${sign}$${profit.toFixed(2)} (${sign}${roi.toFixed(1)}%)`;
  pnlBadge.className='info-pill pnl-badge '+(profit>=0?'pos':'neg');
}

// ---- Chart ----
const TT_W=220,TT_H=160,TT_M=15;
function initChart(){
  if(chart)return;
  chart=LightweightCharts.createChart(chartContainer,{
    layout:{background:{color:'#0F172A'},textColor:'#94A3B8',fontFamily:"'Fira Code',monospace",fontSize:11},
    grid:{vertLines:{color:'rgba(51,65,85,0.3)'},horzLines:{color:'rgba(51,65,85,0.3)'}},
    crosshair:{mode:LightweightCharts.CrosshairMode.Normal,vertLine:{color:'rgba(248,250,252,0.2)',width:1},horzLine:{color:'rgba(248,250,252,0.2)',width:1}},
    rightPriceScale:{borderColor:'#334155',scaleMargins:{top:0.05,bottom:0.05}},
    timeScale:{borderColor:'#334155',timeVisible:true,secondsVisible:true,rightOffset:5},
    handleScroll:{vertTouchDrag:false},
  });
  bidUpSeries=chart.addLineSeries({color:'#22C55E',lineWidth:1.5,title:'Bid UP',priceLineVisible:false,lastValueVisible:true,crosshairMarkerRadius:3});
  bidDnSeries=chart.addLineSeries({color:'#EF4444',lineWidth:1.5,title:'Bid DN',priceLineVisible:false,lastValueVisible:true,crosshairMarkerRadius:3});
  probSeries=chart.addLineSeries({color:'#F59E0B',lineWidth:2,title:'P(UP)',priceLineVisible:false,lastValueVisible:true,crosshairMarkerRadius:3});

  // Tracking tooltip (per LW Charts docs)
  toolTip=document.createElement('div');
  toolTip.style.cssText=`width:${TT_W}px;position:absolute;display:none;padding:10px 14px;box-sizing:border-box;font-size:12px;text-align:left;z-index:1000;top:12px;left:12px;pointer-events:none;border:1px solid #334155;border-radius:8px;font-family:'Fira Code',monospace;-webkit-font-smoothing:antialiased;background:rgba(15,23,42,0.94);color:#F8FAFC;line-height:1.7;`;
  chartContainer.appendChild(toolTip);

  chart.subscribeCrosshairMove(param=>{
    if(param.point===undefined||!param.time||param.point.x<0||param.point.x>chartContainer.clientWidth||param.point.y<0||param.point.y>chartContainer.clientHeight||currentTicks.length===0){
      toolTip.style.display='none';return;
    }
    toolTip.style.display='block';
    const t=param.time;
    let cl=currentTicks[0],md=Math.abs(currentTicks[0].time-t);
    for(let i=1;i<currentTicks.length;i++){const d=Math.abs(currentTicks[i].time-t);if(d<md){md=d;cl=currentTicks[i];}if(d>md)break;}

    const pUp=cl.cal_prob,bUp=cl.bid_up,bDn=cl.bid_dn;
    const edge=(pUp!=null&&bUp!=null)?pUp-bUp:null;
    const pct=v=>v!=null?(v*100).toFixed(2)+'%':'--';
    const edgeFmt=v=>{if(v==null)return'--';const p=(v*100).toFixed(2);return(v>=0?'+':'')+p+'%';};
    const R=(lbl,val,c)=>`<div style="display:flex;justify-content:space-between;gap:12px"><span style="color:#94A3B8">${lbl}</span><span style="font-weight:600;color:${c}">${val}</span></div>`;

    let html=R('P(UP)',pct(pUp),'#F59E0B')+R('Bid UP',pct(bUp),'#22C55E')+R('Bid DN',pct(bDn),'#EF4444')+R('Edge',edgeFmt(edge),edge!=null?(edge>=0?'#22C55E':'#EF4444'):'#94A3B8');

    // Find ALL events near this time (within 3s)
    const nearEvents=eventMarkerData.filter(em=>Math.abs(em.time-t)<3);
    if(nearEvents.length){
      html+=`<div style="margin-top:6px;padding-top:6px;border-top:1px solid #334155;font-size:11px">`;
      for(const ne of nearEvents) html+=fmtEvt(ne.event);
      html+='</div>';
    }
    toolTip.innerHTML=html;
    // Dynamic width based on content
    toolTip.style.width=(nearEvents.length?280:TT_W)+'px';

    let left=param.point.x+TT_M;
    if(left>chartContainer.clientWidth-(nearEvents.length?280:TT_W))left=param.point.x-TT_M-(nearEvents.length?280:TT_W);
    let top=param.point.y+TT_M;
    if(top>chartContainer.clientHeight-TT_H)top=param.point.y-TT_H-TT_M;
    toolTip.style.left=left+'px';toolTip.style.top=top+'px';
  });
  new ResizeObserver(e=>{for(const en of e)chart.resize(en.contentRect.width,en.contentRect.height);}).observe(chartContainer);
}

// ---- Event formatting ----
// Marker legend: ORDER=arrow, FILL=diamond, GATE=x
const EVT_ICONS={order:'\u25B2',fill:'\u25C6',gate:'\u2716'};
function fmtEvt(evt){
  const t=evt.type;
  if(t==='order'){
    const c=evt.side==='UP'?'#22C55E':'#EF4444';
    const icon=EVT_ICONS.order;
    return `<div style="margin:2px 0"><span style="color:${c}">${icon} ORDER ${evt.side}</span> <span style="color:#94A3B8">limit=${(evt.limit*100).toFixed(1)}% $${evt.dollars.toFixed(2)}</span></div><div style="color:#64748B;font-size:10px;margin-left:14px">${evt.reason||''}</div>`;
  }
  if(t==='fill'){
    const c=evt.side==='UP'?'#22C55E':'#EF4444';
    const icon=EVT_ICONS.fill;
    return `<div style="margin:2px 0"><span style="color:${c}">${icon} FILL ${evt.side}</span> <span style="color:#94A3B8">@${(evt.fill_price*100).toFixed(1)}% ${evt.shares.toFixed(1)}sh $${evt.cost.toFixed(2)}</span></div>`;
  }
  if(t.startsWith('gate_')){
    const name=t.replace('gate_','').replace(/_/g,' ').toUpperCase();
    const side=evt.side?` ${evt.side}`:'';
    const icon=EVT_ICONS.gate;
    return `<div style="margin:2px 0"><span style="color:#8B5CF6">${icon} ${name}${side}</span></div>`;
  }
  return `<div style="margin:2px 0;color:#94A3B8">${t}</div>`;
}

// ---- Render ----
function renderChart(ticks,events){
  initChart();
  const bidUpData=[],bidDnData=[],probData=[];
  for(const t of ticks){
    if(t.bid_up!=null)bidUpData.push({time:t.time,value:t.bid_up});
    if(t.bid_dn!=null)bidDnData.push({time:t.time,value:t.bid_dn});
    if(t.cal_prob!=null)probData.push({time:t.time,value:t.cal_prob});
  }
  bidUpSeries.setData(bidUpData);bidDnSeries.setData(bidDnData);probSeries.setData(probData);

  // Build markers — spread across series to avoid overlap
  eventMarkerData=[];
  const mBidUp=[],mBidDn=[],mProb=[];
  if(events.length&&ticks.length){
    const t0=ticks[0].time,tN=ticks[ticks.length-1].time,dur=tN-t0;
    for(const evt of events){
      const evtTime=t0+(evt.time_pct||0)*dur;
      let snap=ticks[0].time,sd=Math.abs(ticks[0].time-evtTime);
      for(let i=1;i<ticks.length;i++){const d=Math.abs(ticks[i].time-evtTime);if(d<sd){sd=d;snap=ticks[i].time;}if(d>sd)break;}

      if(evt.type==='order'){
        // Orders: arrow on the side's bid series
        const arr=evt.side==='UP'?mBidUp:mBidDn;
        arr.push({time:snap,position:'belowBar',color:evt.side==='UP'?'#22C55E':'#EF4444',shape:'arrowUp',size:2});
      }else if(evt.type==='fill'){
        // Fills: square on the side's bid series, above
        const arr=evt.side==='UP'?mBidUp:mBidDn;
        arr.push({time:snap,position:'aboveBar',color:evt.side==='UP'?'#22C55E':'#EF4444',shape:'square',size:1.5});
      }else if(evt.type.startsWith('gate_')){
        // Gates: circle on prob series
        mProb.push({time:snap,position:'belowBar',color:'#8B5CF6',shape:'circle',size:1});
      }else{continue;}
      eventMarkerData.push({time:snap,event:evt});
    }
    mBidUp.sort((a,b)=>a.time-b.time);
    mBidDn.sort((a,b)=>a.time-b.time);
    mProb.sort((a,b)=>a.time-b.time);
  }
  bidUpSeries.setMarkers(mBidUp);
  bidDnSeries.setMarkers(mBidDn);
  probSeries.setMarkers(mProb);

  bidUpSeries.applyOptions({visible:seriesVisible.bid_up});
  bidDnSeries.applyOptions({visible:seriesVisible.bid_dn});
  probSeries.applyOptions({visible:seriesVisible.prob});
  if(refLine){try{probSeries.removePriceLine(refLine);}catch(e){}}
  refLine=probSeries.createPriceLine({price:0.50,color:'rgba(148,163,184,0.4)',lineWidth:1,lineStyle:LightweightCharts.LineStyle.Dashed,axisLabelVisible:true,title:''});
  chart.timeScale().fitContent();
}

function toggleSeries(key){
  seriesVisible[key]=!seriesVisible[key];
  document.querySelector(`.toggle-btn.${key.replace('_','-')}`).classList.toggle('active',seriesVisible[key]);
  ({bid_up:bidUpSeries,bid_dn:bidDnSeries,prob:probSeries})[key]?.applyOptions({visible:seriesVisible[key]});
}
function navCandle(d){const i=selCandle.selectedIndex+d;if(i<0||i>=selCandle.options.length)return;selCandle.selectedIndex=i;onCandleChange();}
function updateNavButtons(){btnPrev.disabled=selCandle.selectedIndex<=0;btnNext.disabled=selCandle.selectedIndex>=selCandle.options.length-1;}
document.addEventListener('keydown',e=>{if(e.target.tagName==='SELECT')return;if(e.key==='ArrowLeft'){navCandle(-1);e.preventDefault();}if(e.key==='ArrowRight'){navCandle(1);e.preventDefault();}});
function updateResolution(o){resBadge.className='resolution-badge';if(o==='UP'){resBadge.textContent='UP';resBadge.classList.add('up');}else if(o==='DN'){resBadge.textContent='DN';resBadge.classList.add('dn');}else{resBadge.textContent='N/A';resBadge.classList.add('na');}}
let loadingEl=null;
function showLoading(s){if(s&&!loadingEl){loadingEl=document.createElement('div');loadingEl.className='loading-overlay';loadingEl.innerHTML='<div class="spinner"></div>';chartContainer.appendChild(loadingEl);}else if(!s&&loadingEl){loadingEl.remove();loadingEl=null;}}
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
