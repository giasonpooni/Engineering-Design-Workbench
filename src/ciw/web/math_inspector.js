"use strict";
(() => {
  const bytes = Uint8Array.from(atob(document.getElementById("net-report").textContent.trim()), c => c.charCodeAt(0));
  const report = JSON.parse(new TextDecoder("utf-8", {fatal: true}).decode(bytes));
  const freeze = value => { if (value && typeof value === "object") { Object.values(value).forEach(freeze); Object.freeze(value); } return value; };
  freeze(report);
  const R = report.retained, D = report.derived, N = R.trace.length;
  const $ = id => document.getElementById(id);
  const text = (id, value) => { $(id).textContent = value; };
  const fmt = (x, digits = 4) => x === null || x === undefined ? "not available" : Number(x).toLocaleString("en-US", {maximumFractionDigits: digits, useGrouping: false});
  const short = value => value.length > 24 ? value.slice(0, 17) + "…" + value.slice(-6) : value;
  const NS = "http://www.w3.org/2000/svg";
  function node(tag, attrs = {}, parent = null, content = null) {
    const el = document.createElementNS(NS, tag);
    for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, String(value));
    if (content !== null) el.textContent = String(content);
    if (parent) parent.appendChild(el);
    return el;
  }
  const line = (p, x1, y1, x2, y2, cls, attrs = {}) => node("line", {x1, y1, x2, y2, class: cls, ...attrs}, p);
  const label = (p, x, y, s, anchor = "start", attrs = {}) => node("text", {x, y, "text-anchor": anchor, ...attrs}, p, s);
  const clear = id => { const el = $(id); el.replaceChildren(); return el; };
  const range = values => {
    const finite = values.filter(x => x !== null && Number.isFinite(x));
    let low = Math.min(...finite), high = Math.max(...finite);
    if (!finite.length) return [-1, 1];
    const pad = (high - low || Math.max(Math.abs(low) * 0.02, 1)) * 0.13;
    return [low - pad, high + pad];
  };
  const scaler = (lo, hi, a, b) => x => a + (x - lo) / (hi - lo || 1) * (b - a);
  function axes(svg, box, xs, ys, xlabel, ylabel) {
    const [left, top, width, height] = box;
    const x = scaler(...xs, left, left + width), y = scaler(...ys, top + height, top);
    for (let j = 0; j <= 4; j++) {
      const yy = top + height * j / 4, val = ys[1] - (ys[1] - ys[0]) * j / 4;
      line(svg, left, yy, left + width, yy, "gridline"); label(svg, left - 9, yy + 4, fmt(val, 3), "end");
    }
    line(svg, left, top + height, left + width, top + height, "axis");
    for (let j = 0; j <= 4; j++) { const val = xs[0] + (xs[1] - xs[0]) * j / 4; label(svg, x(val), top + height + 18, fmt(val, 2), "middle"); }
    label(svg, left + width / 2, top + height + 39, xlabel, "middle"); label(svg, left, top - 9, ylabel);
    return {x, y};
  }
  function tip(el, value) { node("title", {}, el, value); }
  function cross(svg, x, y, size = 4) { line(svg, x-size, y-size, x+size, y+size, "measurement"); line(svg, x-size, y+size, x+size, y-size, "measurement"); }
  function dot(svg, x, y, axis, title, index, r = 4) {
    const el = node("circle", {cx: x, cy: y, r, class: "point " + (axis ? "shell-fill" : "core-fill"), "data-tick": index}, svg);
    tip(el, title); el.addEventListener("click", () => setTick(index)); return el;
  }
  const state = {index: 0, stage: "posterior", radius: 2, matrix: "covariance"};
  function timeChart() {
    const svg = clear("time-chart"), vals = [];
    R.trace.forEach((row, i) => row[state.stage + "_mean"].forEach((v, a) => {
      const s = D[i][state.stage].marginal_sigma?.[a] ?? 0; vals.push(v-state.radius*s, v+state.radius*s);
      if (R.measurements[i][a] !== null) vals.push(R.measurements[i][a]);
    }));
    const width = Math.max(420, Math.min(920, svg.clientWidth));
    svg.setAttribute("viewBox", `0 0 ${width} 260`);
    const xr = range(R.time_s), yr = range(vals), {x,y} = axes(svg, [70,24,width-95,180], xr, yr, "Time in source clock (s)", "Temperature (K)");
    line(svg, x(R.time_s[state.index]), 24, x(R.time_s[state.index]), 204, "cursor");
    R.trace.forEach((row, i) => {
      for (let a=0; a<2; a++) {
        const v = row[state.stage + "_mean"][a], sigma = D[i][state.stage].marginal_sigma?.[a], xx = x(R.time_s[i]), cls = a ? "shell-stroke" : "core-stroke";
        if (sigma !== undefined && sigma !== null) {
          line(svg,xx,y(v-state.radius*sigma),xx,y(v+state.radius*sigma),cls,{"stroke-width":1.5,"opacity":0.7});
          line(svg,xx-4,y(v-state.radius*sigma),xx+4,y(v-state.radius*sigma),cls);
          line(svg,xx-4,y(v+state.radius*sigma),xx+4,y(v+state.radius*sigma),cls);
        }
        dot(svg,xx,y(v),a,`${R.coordinate_order[a]}: ${v} K at ${R.time_s[i]} s`,i,i===state.index?6:4);
        const m=R.measurements[i][a];
        if (m !== null) { const g=node("g",{"data-measurement":`${i}-${a}`},svg); cross(g,xx,y(m)); tip(g,`Measurement ${R.coordinate_order[a]}: ${m} K`); }
        else { label(svg,xx + (a ? 8 : -8),20,a ? "S missing" : "C missing",a ? "start" : "end",{"data-missing":`${i}-${a}`,"font-size":9}); }
      }
    });
  }
  function phaseChart() {
    const svg=clear("phase-chart"), row=R.trace[state.index], mean=row[state.stage+"_mean"], g=D[state.index][state.stage];
    text("ellipse-stage",state.stage.toUpperCase());
    if (!g.unit_contour) { label(svg,210,130,"Contour unavailable: " + g.reason,"middle",{class:"empty"}); text("geometry-summary","Original covariance remains in the matrix panel."); return; }
    const points = g.unit_contour.map(p=>p.map((v,a)=>mean[a]+state.radius*v));
    const observation=R.measurements[state.index], otherStage=state.stage==="posterior"?"predicted":"posterior", otherMean=row[otherStage+"_mean"];
    const xs=points.map(p=>p[0]).concat([otherMean[0],mean[0]]), ys=points.map(p=>p[1]).concat([otherMean[1],mean[1]]);
    if (observation.every(v=>v!==null)) { xs.push(observation[0]); ys.push(observation[1]); }
    let xr=range(xs), yr=range(ys), span=Math.max(xr[1]-xr[0],yr[1]-yr[0]);
    const cx=(xr[0]+xr[1])/2, cy=(yr[0]+yr[1])/2; xr=[cx-span/2,cx+span/2]; yr=[cy-span/2,cy+span/2];
    const {x,y}=axes(svg,[88,27,218,218],xr,yr,"Core temperature (K)","Shell temperature (K)");
    node("polyline",{points:points.map(p=>`${x(p[0])},${y(p[1])}`).join(" "),fill:"#68ddd015",stroke:"#68ddd0","stroke-width":2,"data-contour":"true"},svg);
    node("circle",{cx:x(otherMean[0]),cy:y(otherMean[1]),r:4,fill:"none",stroke:"#9baec5","stroke-width":1.4},svg);
    const pt=node("circle",{cx:x(mean[0]),cy:y(mean[1]),r:5,fill:"#68ddd0",stroke:"#121d2b","stroke-width":2},svg); tip(pt,`Selected ${state.stage} mean`);
    if (observation.every(v=>v!==null)) cross(svg,x(observation[0]),y(observation[1]),5);
    text("geometry-summary",`k = ${state.radius}  |  correlation ρ = ${fmt(g.correlation[0][1],5)}`);
  }
  function matrixTable() {
    const table=$('covariance-table'); table.replaceChildren();
    const matrix=state.matrix==='covariance'?R.trace[state.index][state.stage+'_covariance']:D[state.index][state.stage].correlation;
    const head=document.createElement('tr'); for (const name of ['', 'Core', 'Shell']) {const th=document.createElement('th');th.textContent=name;head.appendChild(th);}table.appendChild(head);
    for(let a=0;a<2;a++){const tr=document.createElement('tr'),th=document.createElement('th');th.textContent=a?'Shell':'Core';tr.appendChild(th);for(let b=0;b<2;b++){const td=document.createElement('td');td.textContent=matrix?fmt(matrix[a][b],6):'unavailable';td.dataset.cell=`${a}-${b}`;if(matrix?.[a][b]<0)td.className='negative';tr.appendChild(td);}table.appendChild(tr);}
    text('eigenvalues',D[state.index][state.stage].principal_variances?.map(v=>fmt(v,6)).join(' / ') ?? 'unavailable');
    text('condition-number',fmt(D[state.index][state.stage].condition_number,4));
  }
  function innovation() {
    const svg=clear('white-chart'), w=D[state.index].whitened, row=R.trace[state.index];
    if(w.status!=='available'){label(svg,190,75,w.reason.replaceAll('_',' '),'middle',{class:'empty'});}
    else {const scale=Math.max(1,...w.components.map(Math.abs))*1.25,x=scaler(-scale,scale,70,360);line(svg,x(0),10,x(0),120,'axis');w.components.forEach((v,i)=>{const y=35+i*46;label(svg,10,y+4,'z'+i);node('rect',{x:Math.min(x(0),x(v)),y:y-10,width:Math.max(.8,Math.abs(x(v)-x(0))),height:20,fill:i?'#e6b473':'#68ddd0'},svg);label(svg,365,y+4,fmt(v,4),'end');});label(svg,200,148,'Cholesky basis · dimensionless','middle');}
    const nis=clear('nis-chart'), vals=R.trace.map(r=>r.nis).filter(x=>x!==null);
    const {x,y}=axes(nis,[55,18,385,88],range(R.time_s),[0,Math.max(1,...vals)*1.25],'Time (s)','NIS · 1');
    line(nis,x(R.time_s[state.index]),18,x(R.time_s[state.index]),106,'cursor');
    R.trace.forEach((r,i)=>{if(r.nis===null){label(nis,x(R.time_s[i]),96,'missing','middle',{'font-size':9});return;}const p=node('circle',{cx:x(R.time_s[i]),cy:y(r.nis),r:i===state.index?6:4,fill:'#94b8ef','data-nis-tick':i},nis);tip(p,`NIS ${r.nis}; active dimension ${r.innovation.length}`);p.addEventListener('click',()=>setTick(i));label(nis,x(R.time_s[i]),y(r.nis)-10,'d='+r.innovation.length,'middle',{'font-size':9});});
    const available=R.measurements[state.index].map((v,a)=>v!==null?(a?'shell':'core'):null).filter(Boolean);
    text('availability',available.length?available.join(' + ').toUpperCase():'NO MEASUREMENTS');
    const target=$('innovation-values');target.replaceChildren();
    for(const [labelText,value] of [['Prior innovation r (K)',row.innovation],['Innovation covariance S (K²)',row.innovation_covariance],['Native conditioning gain matrix',row.gain],['Posterior − prediction (K)',D[state.index].update_delta_k]]){const div=document.createElement('div'),h=document.createElement('h3'),pre=document.createElement('pre');h.textContent=labelText;pre.textContent=JSON.stringify(value,null,2);div.append(h,pre);target.appendChild(div);}
  }
  function designChart(){const svg=clear('design-chart'), candidates=R.selection.candidates, max=Math.max(1e-12,...candidates.map(c=>c.information_gain_nats)),x=scaler(0,max*1.2,100,360);candidates.forEach((c,i)=>{const y=28+i*45,name=c.sensors.length?c.sensors.join(' + '):'none';label(svg,92,y+5,name,'end',{'font-size':10});const selected=c.mask===R.selection.selected_mask;const bar=node('rect',{x:100,y:y-9,width:Math.max(1,x(c.information_gain_nats)-100),height:19,fill:selected?'#68ddd0':c.feasible?'#94b8ef':'#51657e','data-candidate':c.mask},svg);tip(bar,`Gain ${c.information_gain_nats} nats; cost ${c.cost}; feasible ${c.feasible}; selected ${selected}`);label(svg,100,y+27,`${fmt(c.information_gain_nats,4)} nats · cost ${fmt(c.cost)}${!c.feasible?' · infeasible':''}${selected?' · SELECTED':''}`,'start',{'font-size':9});});text('selection-summary',`Budget ${fmt(R.selection_policy.budget)} · provider status ${R.selection.status}`);}
  function addDefinition(target,labelText,value){const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=labelText;dd.textContent=value;target.append(dt,dd);}
  function initial(){
    text('entity',R.entity_id);text('sample-count',`${N} retained ticks · ${R.coordinate_order.length} state coordinates`);
    $('tick').max=String(N-1);
    const p=$('parameters');addDefinition(p,'Heat capacities',R.parameters.capacities_j_per_k.map(v=>fmt(v)).join(' / ')+' J/K');addDefinition(p,'Conductances',R.parameters.conductances_w_per_k.map(v=>fmt(v)).join(' / ')+' W/K');addDefinition(p,'State coordinates',R.coordinate_order.join(' / '));
    for(const name of ['A','B','Ad','Bd']){const div=document.createElement('div'),h=document.createElement('h3'),pre=document.createElement('pre');h.textContent=name;pre.textContent=JSON.stringify(R.model[name],null,2);div.append(h,pre);$('model-matrices').appendChild(div);}
    const b=$('bindings');for(const [name,v] of [['Estimator execution',R.execution_id],['Native result',R.result_id],['Input file SHA-256',report.source.sha256],['Original workspace SHA-256',R.binding.workspace_sha256],['Source clock',R.clock_id],['Frame / ordered coordinates',R.frame],['Display profile',report.producer.profile],['Matrix scope','Per-tick conditional marginals; no cross-tick covariance'],['Noise assumption',R.noise_assumption]])addDefinition(b,name,v);
    designChart();
  }
  function render(){const row=R.trace[state.index],cov=row[state.stage+'_covariance'];text('tick-label',`${state.index+1} / ${N}  ·  t = ${fmt(R.time_s[state.index])} s`);$('tick').setAttribute('aria-valuetext',`Tick ${state.index+1}, ${R.time_s[state.index]} seconds`);$('prev').disabled=state.index===0;$('next').disabled=state.index===N-1;text('metric-mean',row[state.stage+'_mean'].map(v=>fmt(v,3)).join(' / '));text('metric-trace',fmt(cov[0][0]+cov[1][1],5));text('metric-nis',row.nis===null?'MISSING':fmt(row.nis,5));text('metric-dimension',`${row.innovation.length} active measurement coordinates`);text('metric-gain',fmt(D[state.index].conditioning_gain_nats,5));timeChart();phaseChart();matrixTable();innovation();text('raw-tick',JSON.stringify({retained:row,measurements:R.measurements[state.index],derived:D[state.index],authority:report.authority},null,2));document.body.dataset.tick=String(state.index);document.body.dataset.stage=state.stage;}
  function setTick(i){state.index=Math.max(0,Math.min(N-1,i));$('tick').value=String(state.index);render();}
  $('tick').addEventListener('input',e=>setTick(Number(e.target.value)));$('prev').addEventListener('click',()=>setTick(state.index-1));$('next').addEventListener('click',()=>setTick(state.index+1));$('stage').addEventListener('change',e=>{state.stage=e.target.value;render();});$('radius').addEventListener('change',e=>{state.radius=Number(e.target.value);render();});$('matrix-mode').addEventListener('change',e=>{state.matrix=e.target.value;matrixTable();});
  $('download-report').addEventListener('click',()=>{const blob=new Blob([new TextDecoder('utf-8',{fatal:true}).decode(bytes)],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='thermal-math-inspection.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
  let resizeFrame = null;
  window.addEventListener('resize',()=>{cancelAnimationFrame(resizeFrame);resizeFrame=requestAnimationFrame(render);});
  initial();render();document.body.dataset.ready='true';
})();
