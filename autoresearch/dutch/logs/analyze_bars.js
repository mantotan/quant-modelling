const fs = require('fs');
const path = require('path');
const TEMP = process.env.TEMP || process.env.TMP || 'C:\\Users\\user\\AppData\\Local\\Temp';

function analyze(file, tf) {
  const fpath = path.join(TEMP, file);
  const lines = fs.readFileSync(fpath, 'utf8').trim().split('\n');
  let negShares = 0, zeroFill = 0, highCost = 0, totalPc = 0, totalProfit = 0;
  const rows = [];
  for (const l of lines) {
    try {
      const b = JSON.parse(l);
      const inv = b.inventory || {}; const cost = b.cost || {}; const pnl = b.pnl || {}; const fill = b.fill_stats || {};
      const up = inv.up_shares || 0; const dn = inv.dn_shares || 0; const matched = inv.matched || 0;
      const pc = cost.avg_pair_cost || 1.0; const placed = fill.orders_placed || 0; const filled = fill.orders_filled || 0;
      if (up < 0 || dn < 0) negShares++;
      if (placed > 0 && filled === 0) zeroFill++;
      if (pc > 0.98) highCost++;
      totalPc += pc; totalProfit += (pnl.profit || 0);
      const fr = placed > 0 ? (filled/placed*100).toFixed(0) : 'N/A';
      rows.push(b.bar_id + ' ' + b.outcome + ' pc=' + pc.toFixed(3) + ' P=' + (pnl.profit||0).toFixed(2) + ' up=' + up.toFixed(1) + ' dn=' + dn.toFixed(1) + ' m=' + matched.toFixed(1) + ' fr=' + fr + '%');
    } catch(e) {}
  }
  const n = rows.length;
  console.log('=== ' + tf + ' ===');
  rows.forEach(r => console.log('  ' + r));
  console.log('  SUMMARY avg_pc=' + (totalPc/n).toFixed(3) + ' total_profit=' + totalProfit.toFixed(2) + ' neg_shares=' + negShares + ' zeroFill=' + zeroFill + ' highCost=' + highCost);
}
analyze('bars5m.jsonl', '5m');
analyze('bars15m.jsonl', '15m');
