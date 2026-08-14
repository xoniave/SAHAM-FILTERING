const state={scanner:[],selected:null,chartLayers:{levels:true,ma:true,structure:true,patterns:true},chart:null,candleSeries:null,scanPoll:null,lastScanStarted:null};
const $=s=>document.querySelector(s);const $$=s=>[...document.querySelectorAll(s)];
const fmt=n=>n==null||Number.isNaN(Number(n))?'—':new Intl.NumberFormat('id-ID',{maximumFractionDigits:2}).format(Number(n));
const pct=n=>n==null?'—':`${n>=0?'+':''}${Number(n).toFixed(2)}%`;
const formatDate=d=>{if(!d)return '—';try{return new Intl.DateTimeFormat('id-ID',{day:'2-digit',month:'short',year:'numeric'}).format(new Date(d+'T00:00:00'))}catch{return d}};
const confidenceLabel=x=>({HIGH:'TINGGI',MEDIUM:'SEDANG',LOW:'RENDAH','—':'—'}[x]||x||'—');
function decisionLabel(d=''){
  return d
    .replace(/^READY — /,'SIAP — ')
    .replace(/^WATCH — /,'PANTAU — ')
    .replace(/^WATCH$/,'PANTAU')
    .replace(/^WAIT$/,'TUNGGU')
    .replace(/^AVOID$/,'HINDARI')
    .replace(/^SELL \/ EXIT$/,'JUAL / EXIT')
    .replace(/^SELL ON STRENGTH WATCH$/,'PANTAU SELL ON STRENGTH')
    .replace(/^SELL ON STRENGTH$/,'SELL ON STRENGTH')
    .replace(/^HOLD — CAUTION$/,'HOLD — WASPADA')
    .replace(/^DO NOT CHASE — NEAR RESISTANCE$/,'JANGAN KEJAR — DEKAT RESISTANCE')
    .replace(/^DO NOT CHASE — BREAKOUT TOO FAR$/,'JANGAN KEJAR — BREAKOUT SUDAH TERLALU JAUH')
    .replace(/^ENTRY EXPIRED — WAIT RETRACEMENT$/,'ENTRY SUDAH LEWAT — TUNGGU RETRACEMENT')
    .replace(/^DATA ERROR$/,'DATA ERROR');
}
const badgeClass=d=>d.includes('READY')?'ready':d.includes('HOLD')?'hold':(d.includes('SELL')||d.includes('AVOID')||d.includes('ERROR')||d.includes('DO NOT CHASE'))?'danger':'watch';
async function api(url,options){const r=await fetch(url,options);if(!r.ok){let msg=r.statusText;try{msg=(await r.json()).detail||msg}catch{}throw new Error(msg)}return r.json()}

function autoUpdateText(s){
  if(!s.auto_eod_sync)return 'Pembaruan EOD otomatis: MATI';
  const mins=Math.round((s.auto_eod_check_seconds||1200)/60);
  const st=s.auto_sync||{};
  if(st.status==='checking')return 'Pembaruan EOD: sedang memeriksa…';
  if(st.status==='error')return 'Pembaruan EOD: cek gagal';
  return `Pembaruan EOD otomatis: AKTIF • cek ±${mins} menit`;
}
async function loadStatus(){
  const s=await api('/api/status');
  const session=s.latest_session?` • Sesi ${formatDate(s.latest_session)}`:'';
  const liveLabel=s.is_live?'LIVE':(s.analysis_enabled?'EOD NYATA':'ANALISIS DIMATIKAN');
  $('#providerBadge').textContent=`${liveLabel} • Universe ${s.universe_count}${session}`;
  $('#providerBadge').style.color=s.is_live?'var(--good)':(s.analysis_enabled?'var(--warn)':'var(--bad)');
  $('#autoUpdateBadge').textContent=autoUpdateText(s);
  const n=$('#dataNotice');
  if(s.sync_required){
    n.style.display='block';
    n.innerHTML=`<b>Data EOD belum lengkap.</b> Jalankan <code>SYNC_REAL_DATA.bat</code>. History tersedia untuk ${s.history_cached_count} saham.`;
  }else if(s.analysis_enabled && !s.is_live){
    n.style.display='block';
    n.innerHTML=`<b>Mode EOD nyata.</b> Analisis memakai candle dari <b>sesi yang sudah selesai</b>${s.latest_session?' ('+formatDate(s.latest_session)+')':''}. Artinya harga yang bergerak di Stockbit <b>hari ini belum masuk</b> sampai sesi dianggap final. Sistem memeriksa EOD baru otomatis; sebelum 18:00 WIB provider sengaja memakai sesi sebelumnya agar candle hari berjalan tidak dianggap final.`;
  }else if(!s.analysis_enabled){
    n.style.display='block';n.innerHTML=`<b>Mode demo.</b> Keputusan entry/exit dimatikan agar data synthetic tidak terlihat sebagai signal nyata.`;
  }else n.style.display='none';
  return s;
}

function switchTab(name){$$('.tab').forEach(b=>b.classList.toggle('active',b.dataset.tab===name));$$('.view').forEach(v=>v.classList.remove('active'));$(`#view-${name}`).classList.add('active');if(name==='portfolio')loadPortfolio();if(name==='rules')loadRules();if(name==='classify')loadClassifications()}
$$('.tab').forEach(b=>b.addEventListener('click',()=>switchTab(b.dataset.tab)));

async function loadScanner(){
  $('#scannerStatus').textContent=state.scanner.length?'Memperbarui snapshot…':'Memuat scanner…';
  try{
    const rows=await api('/api/scanner?limit=1200');
    if(rows.length||!state.scanner.length)state.scanner=rows;
    renderScanner();
  }catch(e){$('#scannerStatus').textContent='Error: '+e.message}
}
function filterDecision(row,f){if(!f)return true;return (row.decision||'').includes(f)}
function renderScanner(){
  const q=$('#searchInput').value.trim().toLowerCase();const f=$('#decisionFilter').value;
  const rows=state.scanner.filter(x=>(!q||x.symbol?.toLowerCase().includes(q)||x.name?.toLowerCase().includes(q))&&filterDecision(x,f));
  $('#scannerStatus').textContent=`${rows.length} saham ditampilkan dari ${state.scanner.length}`;
  const all=state.scanner;
  const counts={ready:all.filter(x=>x.decision?.startsWith('READY')).length,watch:all.filter(x=>x.decision?.startsWith('WATCH')).length,hold:all.filter(x=>x.decision?.includes('HOLD')).length,risk:all.filter(x=>x.decision?.includes('SELL')||x.decision==='AVOID').length};
  $('#scannerMetrics').innerHTML=`<div class="metric"><div class="muted">Siap Entry</div><div class="num">${counts.ready}</div></div><div class="metric"><div class="muted">Pantau</div><div class="num">${counts.watch}</div></div><div class="metric"><div class="muted">Hold</div><div class="num">${counts.hold}</div></div><div class="metric"><div class="muted">Jual / Hindari</div><div class="num">${counts.risk}</div></div>`;
  $('#scannerBody').innerHTML=rows.map(x=>`<tr data-symbol="${x.symbol}"><td><div class="sym">${x.symbol}</div><div class="name">${x.name||''}</div></td><td>${fmt(x.last)}</td><td class="${(x.change_pct??0)>=0?'pos':'neg'}">${pct(x.change_pct)}</td><td>${x.macro_cycle||'—'}</td><td>${x.trend||'—'}</td><td>${x.rvol!=null?Number(x.rvol).toFixed(2)+'x':'—'}</td><td>${(x.patterns||[]).join(', ')||'—'}</td><td><span class="badge ${badgeClass(x.decision||'')}">${decisionLabel(x.decision||'—')}</span></td><td>${confidenceLabel(x.confidence)}</td></tr>`).join('');
  $$('#scannerBody tr[data-symbol]').forEach(r=>r.addEventListener('click',()=>openDetail(r.dataset.symbol)));
}
$('#decisionFilter').addEventListener('change',renderScanner);$('#searchInput').addEventListener('input',renderScanner);

function renderScanProgress(s){
  const pctv=Math.max(0,Math.min(100,Number(s.percent||0)));
  $('#scanProgressPct').textContent=`${pctv.toFixed(1)}%`;
  $('#scanProgressBar').style.width=`${pctv}%`;
  $('#scanProgressTitle').textContent=s.status==='running'?'Scanner sedang berjalan':s.status==='done'?'Scan selesai':s.status==='error'?'Scan gagal':'Status Scanner';
  $('#scanProgressText').textContent=s.message||'—';
  $('#scanProgressCard').classList.toggle('running',s.status==='running');
}
async function checkScanStatus(){
  try{
    const s=await api('/api/scan/status');
    if(s.started_at && s.started_at!==state.lastScanStarted){state.lastScanStarted=s.started_at;checkScanStatus.loadedDone=false}
    renderScanProgress(s);
    if(s.status==='running'){
      if(!state.scanPoll)state.scanPoll=setInterval(checkScanStatus,700);
    }else{
      if(state.scanPoll){clearInterval(state.scanPoll);state.scanPoll=null}
      if(s.status==='done'&&!checkScanStatus.loadedDone){checkScanStatus.loadedDone=true;await loadScanner();await loadClassifications()}
    }
  }catch(e){$('#scanProgressText').textContent='Gagal membaca progres: '+e.message}
}
$('#refreshScanner').addEventListener('click',async()=>{
  checkScanStatus.loadedDone=false;
  try{const s=await api('/api/scan/start',{method:'POST'});renderScanProgress(s);if(!state.scanPoll)state.scanPoll=setInterval(checkScanStatus,700)}catch(e){alert('Gagal memulai scan: '+e.message)}
});

async function loadClassifications(){
  const g=await api('/api/classifications');
  $('#classificationGrid').innerHTML=Object.entries(g).sort((a,b)=>b[1].length-a[1].length).map(([name,rows])=>`<div class="card class-card"><h3>${decisionLabel(name)} <span class="muted">(${rows.length})</span></h3><div class="class-list">${rows.slice(0,40).map(x=>`<div class="class-item" data-symbol="${x.symbol}"><div><b>${x.symbol}</b><div class="name">${x.macro_cycle||''}</div></div><div>${fmt(x.last)}</div></div>`).join('')}</div></div>`).join('');
  $$('#classificationGrid [data-symbol]').forEach(x=>x.addEventListener('click',()=>openDetail(x.dataset.symbol)));
}
$('#refreshClasses').addEventListener('click',loadClassifications);

async function loadPortfolio(){const rows=await api('/api/portfolio');$('#portfolioBody').innerHTML=rows.map(p=>`<tr data-symbol="${p.symbol}"><td class="sym">${p.symbol}</td><td>${fmt(p.average_entry)}</td><td>${fmt(p.last)}</td><td class="${(p.pnl_pct||0)>=0?'pos':'neg'}">${pct(p.pnl_pct||0)}</td><td>${p.lots}</td><td>${p.style}</td><td>${p.cycle?.macro||'—'}</td><td><span class="badge ${badgeClass(p.decision?.decision||'')}">${decisionLabel(p.decision?.decision||p.error||'—')}</span></td><td><button class="btn pf-del" data-id="${p.id}">Hapus</button></td></tr>`).join('');$$('#portfolioBody tr[data-symbol]').forEach(r=>r.addEventListener('click',e=>{if(!e.target.classList.contains('pf-del'))openDetail(r.dataset.symbol)}));$$('.pf-del').forEach(b=>b.addEventListener('click',async e=>{e.stopPropagation();await api(`/api/portfolio/${b.dataset.id}`,{method:'DELETE'});loadPortfolio()}))}
$('#pfAdd').addEventListener('click',async()=>{const payload={symbol:$('#pfSymbol').value.trim().toUpperCase(),average_entry:Number($('#pfEntry').value),lots:Number($('#pfLots').value),style:$('#pfStyle').value};if(!payload.symbol||!payload.average_entry||!payload.lots)return alert('Lengkapi kode saham, average entry, dan lot.');await api('/api/portfolio',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});$('#pfSymbol').value=$('#pfEntry').value=$('#pfLots').value='';loadPortfolio()});

async function loadRules(){const rules=await api('/api/rulebook');$('#ruleGrid').innerHTML=rules.map(r=>`<div class="card rule-card"><h3>${r.title}</h3><ul>${r.items.map(i=>`<li>${i}</li>`).join('')}</ul></div>`).join('')}

const levelLabel=x=>({'Active Support':'Support Aktif','Major Support':'Support Mayor','Active Resistance':'Resistance Aktif','Major Resistance':'Resistance Mayor'}[x]||x);
function levelHtml(rows){return rows.length?rows.map(x=>`<div class="level-row"><div><b>${levelLabel(x.label||x.kind)}</b><div class="name">${x.sources.join(' + ')} • ${x.touches} sentuhan</div></div><div>${fmt(x.price)}<div class="name">skor ${x.score}</div></div></div>`).join(''):'<div class="empty">Belum ada level valid.</div>'}
function qualityLabel(q){return ({Higher:'Lebih kuat',Candidate:'Kandidat','Context required':'Perlu konteks'}[q]||q)}
function patternHtml(rows){return rows.length?rows.slice().reverse().map(p=>{const age=p.age_bars??'—';const fresh=p.fresh_for_entry?'<span class="fresh-tag">FRESH UNTUK ENTRY</span>':'<span class="history-tag">HISTORIS • BUKAN TRIGGER ENTRY</span>';return `<div class="pattern-row"><div class="pattern-name">${p.name}</div><div class="name">${p.group} • ${qualityLabel(p.quality)} • ${age} candle lalu</div><div class="pattern-freshness">${fresh}</div><div class="small muted">${p.reason}</div></div>`}).join(''):'<div class="empty">Tidak ada pola yang memenuhi rule pada window terbaru.</div>'}

async function openDetail(symbol){$('#drawerBackdrop').classList.add('open');$('#detailDrawer').classList.add('open');$('#detailSymbol').textContent=symbol;$('#detailName').textContent='Memuat…';$('#priceChart').innerHTML='<div class="chart-loading">Memuat chart…</div>';try{const a=await api(`/api/analyze/${symbol}`);state.selected=a;renderDetail(a)}catch(e){$('#detailName').textContent='Error: '+e.message;$('#priceChart').innerHTML=`<div class="chart-loading error">${e.message}</div>`}}
function closeDetail(){$('#drawerBackdrop').classList.remove('open');$('#detailDrawer').classList.remove('open');$('#detailLayout').classList.remove('chart-focus');$('#expandChart').textContent='Perbesar Chart';destroyChart()}
$('#drawerBackdrop').addEventListener('click',closeDetail);$('#closeDrawer').addEventListener('click',closeDetail);document.addEventListener('keydown',e=>{if(e.key==='Escape')closeDetail()});

function renderDetail(a){
  const row=state.scanner.find(x=>x.symbol===a.symbol);$('#detailName').textContent=row?.name||'';const src=a.data_source?`${a.data_source.data_mode}${a.data_source.is_live?' • LIVE':' • EOD'}`:'';$('#detailSubtitle').textContent=`${a.cycle.macro} • ${a.cycle.local} • ${a.structure.trend} ${a.structure.state}${src?' • '+src:''}`;
  $('#detailMetrics').innerHTML=`<div class="metric"><div class="muted">Harga Terakhir</div><div class="num">${fmt(a.quote.last)}</div><div class="${a.quote.change_pct>=0?'pos':'neg'}">${pct(a.quote.change_pct)}</div></div><div class="metric"><div class="muted">RVOL</div><div class="num">${a.volume.rvol?Number(a.volume.rvol).toFixed(2)+'x':'—'}</div><div>${a.volume.high_volume?'HIGH VOLUME':'≤ Volume MA20'}</div></div><div class="metric"><div class="muted">Siklus Makro</div><div class="num smaller">${a.cycle.macro}</div></div><div class="metric"><div class="muted">Trend</div><div class="num smaller">${a.structure.trend}</div><div>${a.structure.state}</div></div><div class="metric"><div class="muted">Price + Volume</div><div class="num smaller">${a.volume.classification}</div></div>`;
  const d=a.decision;$('#decisionBox').innerHTML=`<div class="decision-main">${decisionLabel(d.decision)}</div><div class="badge ${badgeClass(d.decision)}">KEYAKINAN ${confidenceLabel(d.confidence)}</div>`;$('#reasonList').innerHTML=d.reasons.map(x=>`<li>${x}</li>`).join('')||'<li>—</li>';$('#warningList').innerHTML=d.warnings.map(x=>`<li>${x}</li>`).join('')||'<li class="muted">Tidak ada peringatan utama.</li>';$('#nextTrigger').textContent=d.next_trigger;$('#supportList').innerHTML=levelHtml(a.levels.supports);$('#resistanceList').innerHTML=levelHtml(a.levels.resistances);$('#patternList').innerHTML=patternHtml(a.patterns);$('#chartStageBadge').textContent=`Siklus saat ini: ${a.cycle.macro}`;renderChart(a);
}

['toggleLevels','toggleMA','toggleStructure','togglePatterns'].forEach(id=>$('#'+id).addEventListener('change',e=>{state.chartLayers[id.replace('toggle','').toLowerCase()]=e.target.checked;if(state.selected)renderChart(state.selected)}));

function destroyChart(){if(state.chart){try{state.chart.remove()}catch{}state.chart=null;state.candleSeries=null}}
function chartTime(v){return String(v).slice(0,10)}
function renderChart(a){
  destroyChart();const container=$('#priceChart');container.innerHTML='';
  const L=window.LightweightCharts;
  if(!L){container.innerHTML='<div class="chart-loading error">Library chart belum termuat. Pastikan internet aktif, lalu refresh halaman.</div>';return}
  const bars=a.bars||[];if(!bars.length){container.innerHTML='<div class="chart-loading error">Data OHLCV tidak tersedia.</div>';return}
  const chart=L.createChart(container,{width:container.clientWidth,height:container.clientHeight||620,layout:{background:{type:'solid',color:'#0a1118'},textColor:'#8da0b3',fontFamily:'Inter, Segoe UI, Arial'},grid:{vertLines:{color:'#172431'},horzLines:{color:'#172431'}},crosshair:{mode:L.CrosshairMode?.MagnetOHLC??0},rightPriceScale:{borderColor:'#2b3948',scaleMargins:{top:.08,bottom:.22}},timeScale:{borderColor:'#2b3948',timeVisible:false,secondsVisible:false,rightOffset:8,barSpacing:7,minBarSpacing:2},handleScroll:{mouseWheel:true,pressedMouseMove:true,horzTouchDrag:true,vertTouchDrag:true},handleScale:{axisPressedMouseMove:true,mouseWheel:true,pinch:true}});
  state.chart=chart;
  const candle=chart.addSeries(L.CandlestickSeries,{upColor:'#2ec7a6',downColor:'#ef6464',borderVisible:false,wickUpColor:'#2ec7a6',wickDownColor:'#ef6464',priceLineVisible:true,lastValueVisible:true});state.candleSeries=candle;
  candle.setData(bars.map(b=>({time:chartTime(b.timestamp),open:b.open,high:b.high,low:b.low,close:b.close})));
  const volume=chart.addSeries(L.HistogramSeries,{priceFormat:{type:'volume'},priceScaleId:'volume',lastValueVisible:false,priceLineVisible:false});
  volume.priceScale().applyOptions({scaleMargins:{top:.82,bottom:0}});
  volume.setData(bars.map(b=>({time:chartTime(b.timestamp),value:b.volume,color:b.close>=b.open?'rgba(46,199,166,.42)':'rgba(239,100,100,.42)'})));

  if(state.chartLayers.ma){
    const defs=[['ma20','#ef6464','MA20'],['ma50','#568cff','MA50'],['ma100','#99d44b','MA100'],['ma200','#db4baf','MA200']];
    defs.forEach(([k,color,title])=>{const s=chart.addSeries(L.LineSeries,{color,lineWidth:1.5,priceLineVisible:false,lastValueVisible:false,title});s.setData(bars.filter(b=>b[k]!=null).map(b=>({time:chartTime(b.timestamp),value:b[k]})))});
  }
  if(state.chartLayers.levels){
    (a.levels.supports||[]).slice(0,4).forEach((l,i)=>candle.createPriceLine({price:l.price,color:i===0?'#69a8ff':'rgba(105,168,255,.65)',lineWidth:i===0?2:1,lineStyle:L.LineStyle?.Dashed??2,axisLabelVisible:true,title:levelLabel(l.label||'Support')}));
    (a.levels.resistances||[]).slice(0,4).forEach((l,i)=>candle.createPriceLine({price:l.price,color:i===0?'#f4c95d':'rgba(244,201,93,.65)',lineWidth:i===0?2:1,lineStyle:L.LineStyle?.Dashed??2,axisLabelVisible:true,title:levelLabel(l.label||'Resistance')}));
  }
  const available=new Set(bars.map(b=>chartTime(b.timestamp)));const markers=[];
  (a.annotations||[]).forEach(z=>{const t=chartTime(z.timestamp);if(!available.has(t))return;
    if(z.kind==='structure'&&state.chartLayers.structure){const high=String(z.label).includes('H');markers.push({time:t,position:high?'aboveBar':'belowBar',color:high?'#69a8ff':'#f4c95d',shape:'circle',text:z.label,size:1})}
    if(z.kind==='breakout'&&state.chartLayers.levels)markers.push({time:t,position:'belowBar',color:'#48d08f',shape:'arrowUp',text:'Breakout',size:1.5});
    if(z.kind==='breakdown'&&state.chartLayers.levels)markers.push({time:t,position:'aboveBar',color:'#ff7171',shape:'arrowDown',text:'Breakdown',size:1.5});
    if(z.kind==='pattern'&&state.chartLayers.patterns){const bullish=String(z.group||'').startsWith('Bullish');markers.push({time:t,position:bullish?'belowBar':'aboveBar',color:'#b68cff',shape:bullish?'arrowUp':'arrowDown',text:z.label,size:1})}
  });
  markers.sort((x,y)=>String(x.time).localeCompare(String(y.time)));
  if(L.createSeriesMarkers)try{L.createSeriesMarkers(candle,markers)}catch(e){console.warn('Markers:',e)}
  chart.timeScale().fitContent();
  $('#chartLegend').innerHTML=`<span>Harga: ${fmt(a.quote.last)}</span><span>MA20: ${fmt(a.indicators.ma20)}</span><span>MA50: ${fmt(a.indicators.ma50)}</span><span>MA100: ${fmt(a.indicators.ma100)}</span><span>MA200: ${fmt(a.indicators.ma200)}</span><span>Volume MA20: ${fmt(a.volume.ma20)}</span>`;
  const ro=new ResizeObserver(()=>{if(state.chart&&container.clientWidth>0)state.chart.resize(container.clientWidth,container.clientHeight||620)});ro.observe(container);chart.__ro=ro;
}
function logicalRange(lastBars){if(!state.chart||!state.selected)return;const n=state.selected.bars.length;state.chart.timeScale().setVisibleLogicalRange({from:Math.max(0,n-lastBars),to:n+3})}
$('#range6m').addEventListener('click',()=>logicalRange(126));$('#range1y').addEventListener('click',()=>logicalRange(220));$('#rangeAll').addEventListener('click',()=>state.chart?.timeScale().fitContent());$('#fitChart').addEventListener('click',()=>state.chart?.timeScale().fitContent());
$('#expandChart').addEventListener('click',()=>{const layout=$('#detailLayout');const on=layout.classList.toggle('chart-focus');$('#expandChart').textContent=on?'Kembalikan':'Perbesar Chart';setTimeout(()=>{if(state.chart){const c=$('#priceChart');state.chart.resize(c.clientWidth,c.clientHeight)}},50)});

Promise.all([loadStatus(),loadScanner(),checkScanStatus()]).catch(console.error);
setInterval(()=>loadStatus().catch(console.error),60000);
setInterval(()=>checkScanStatus().catch?.(console.error),10000);
