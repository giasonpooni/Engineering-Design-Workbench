'use strict';
const $ = id => document.getElementById(id);
const state = {catalog:[], example:null, csrf:'', job:null, original:null, result:null, source:null, busy:false, sequence:0};
// Display preferences and plot paint are separate from evidence and execution.
const contrastPreferenceKey = 'net.visual-contrast.v1';
const contrastQuery = window.matchMedia('(prefers-contrast: more)');
let explicitContrast = null;
try {const saved=localStorage.getItem(contrastPreferenceKey);if(saved==='high'||saved==='standard')explicitContrast=saved;} catch {}
function applyContrast(mode){
  document.documentElement.dataset.contrast=mode;
  $('contrast-toggle').setAttribute('aria-pressed',String(mode==='high'));
  $('contrast-value').textContent=mode==='high'?'On':'Off';
}
applyContrast(explicitContrast||(contrastQuery.matches?'high':'standard'));
$('contrast-toggle').addEventListener('click',()=>{
  explicitContrast=document.documentElement.dataset.contrast==='high'?'standard':'high';
  applyContrast(explicitContrast);
  try {localStorage.setItem(contrastPreferenceKey,explicitContrast);} catch {}
});
contrastQuery.addEventListener('change',event=>{if(explicitContrast===null)applyContrast(event.matches?'high':'standard');});
const plotTones=['estimate','observation','innovation','response','reference'];
const plotColorTones={'#96f6ca':'estimate','#ffbb82':'observation','#93bcff':'innovation','#c6a7ff':'response','#ffd78b':'reference'};
const seriesTone=(series,index)=>plotColorTones[series.color]||plotTones[index%plotTones.length];
const seriesColor=(series,index)=>`var(--plot-${seriesTone(series,index)})`;
const number = v => typeof v === 'number' && Number.isFinite(v) ? Number(v.toPrecision(5)).toString() : '—';
const pretty = value => JSON.stringify(value,null,2);
function node(tag, cls, text) {const n=document.createElement(tag); if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n;}
async function api(path, method='GET', body) {
  const options={method,headers:{Accept:'application/json'},credentials:'same-origin',cache:'no-store'};
  if(method!=='GET'){options.headers['Content-Type']='application/json';options.headers['X-CSRF-Token']=state.csrf;options.body=pretty(body||{});}
  const response=await fetch(path,options); const data=await response.json();
  if(!response.ok){const err=data.error||data;throw new Error((err.message||'The request failed.')+(err.action?' '+err.action:''));}return data;
}
function showError(id,error) {$(id).textContent=error.message||String(error);$(id).hidden=false;}
function clearError(id){$(id).hidden=true;$(id).textContent='';}
function setStatus(text,status=''){$('execution-status').textContent=text;$('execution-status').className='execution-status '+status;}
function setBusy(busy){state.busy=busy;$('run').disabled=busy||!state.example;$('reset').disabled=busy;$('cancel').hidden=!busy;$('replay').disabled=busy||!state.original;for(const button of $('examples').children)button.disabled=busy;for(const input of $('parameters').querySelectorAll('input'))input.disabled=busy;}
function selectExample(example){
  state.sequence++;state.example=example;state.job=null;state.original=null;state.result=null;state.source=null;
  $('result-content').hidden=true;$('empty-state').hidden=false;$('result-state').textContent='Awaiting execution';$('config-export').disabled=true;
  $('source-preview').textContent='Run an example to inspect its executed declaration.';clearError('run-error');
  for(const button of $('examples').children)button.setAttribute('aria-pressed',String(button.dataset.example===example.id));
  $('example-summary').textContent=example.summary;
  $('parameters').replaceChildren();
  for(const p of example.parameters||[]){
    const label=node('label','parameter');label.htmlFor='parameter-'+p.id;const row=node('span','label-row');row.append(node('span','',p.label),node('span','unit',p.unit||'×'));
    const input=node('input');input.id='parameter-'+p.id;input.name=p.id;input.type='number';input.min=p.min;input.max=p.max;input.step=p.step||'any';input.value=p.default;input.required=true;input.setAttribute('aria-describedby','help-'+p.id);
    const help=node('span','help',p.help);help.id='help-'+p.id;label.append(row,input,help);$('parameters').append(label);
  }
  const dl=node('dl');const problem=example.problem||{};
  for(const [key,label] of [['state','State'],['dynamics','Dynamics'],['sensors','Observations'],['uncertainty','Uncertainty'],['timing','Timing']]){if(problem[key]!==undefined){dl.append(node('dt','',label),node('dd','',Array.isArray(problem[key])?problem[key].join('; '):typeof problem[key]==='object'?pretty(problem[key]):problem[key]));}}
  $('declaration').replaceChildren(dl);const limits=problem.limitations||example.limitations;if(limits)$('declaration').append(node('p','limitations',Array.isArray(limits)?limits.join(' '):limits));
  setStatus('Ready to execute '+example.name+'.');setBusy(false);
}
function params(){return Object.fromEntries([...$('parameters').querySelectorAll('input')].map(input=>[input.name,Number(input.value)]));}
function svgElement(tag,attrs={},text){const e=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [k,v] of Object.entries(attrs))e.setAttribute(k,String(v));if(text!==undefined)e.textContent=text;return e;}
function renderPlot(plot,index){
  const card=node('section','plot panel');const head=node('div','plot-header');head.append(node('h3','',plot.title),node('span','plot-unit',plot.y_label||''));card.append(head);
  const series=plot.series||[];const legend=node('div','legend');series.forEach((s,i)=>{const item=node('span','legend-item'),mark=node('span','legend-mark '+s.kind);mark.style.backgroundColor=seriesColor(s,i);mark.style.color=seriesColor(s,i);mark.dataset.tone=seriesTone(s,i);item.append(mark,node('span','',s.name));legend.append(item);});card.append(legend);
  const svg=svgElement('svg',{viewBox:'0 0 760 310',class:'plot-svg',role:'img','aria-labelledby':'plot-title-'+index+' plot-description-'+index});
  svg.append(svgElement('title',{id:'plot-title-'+index},plot.title),svgElement('desc',{id:'plot-description-'+index},plot.help||'Observations, estimates and conditional uncertainty from the retained execution.'));
  const all=series.flatMap(s=>(s.points||[]).filter(p=>p.y!==null&&Number.isFinite(p.x)&&Number.isFinite(p.y)));if(!all.length){card.append(node('p','support','No values were observed for this plot.'));return card;}
  let xmin=Math.min(...all.map(p=>p.x)),xmax=Math.max(...all.map(p=>p.x)),ymin=Math.min(...all.map(p=>p.lower??p.y)),ymax=Math.max(...all.map(p=>p.upper??p.y));
  const xd=xmax-xmin||1,yd=ymax-ymin||Math.max(Math.abs(ymax)*.01,1);xmin-=xd*.04;xmax+=xd*.04;ymin-=yd*.13;ymax+=yd*.13;
  if(plot.equal_scale){const ratio=664/226,cx=(xmin+xmax)/2,cy=(ymin+ymax)/2;const width=Math.max(xmax-xmin,(ymax-ymin)*ratio),height=width/ratio;xmin=cx-width/2;xmax=cx+width/2;ymin=cy-height/2;ymax=cy+height/2;}
  const X=x=>68+(x-xmin)/(xmax-xmin)*664,Y=y=>252-(y-ymin)/(ymax-ymin)*226;
  for(let j=0;j<=4;j++){const y=ymin+(ymax-ymin)*j/4;svg.append(svgElement('line',{x1:68,x2:732,y1:Y(y),y2:Y(y),class:'plot-grid',stroke:'var(--plot-grid)','stroke-width':1}),svgElement('text',{x:57,y:Y(y)+4,'text-anchor':'end',class:'plot-label',fill:'var(--plot-label)','font-size':13},number(y)));const x=xmin+(xmax-xmin)*j/4;svg.append(svgElement('text',{x:X(x),y:274,'text-anchor':'middle',class:'plot-label',fill:'var(--plot-label)','font-size':13},number(x)));}
  svg.append(svgElement('text',{x:400,y:303,'text-anchor':'middle',class:'plot-label',fill:'var(--plot-label)','font-size':13},plot.x_label||'Time (s)'));
  series.forEach((s,i)=>{const color=seriesColor(s,i),tone=seriesTone(s,i),points=s.points||[];let segments=[],current=[];for(const p of points){if(p.y!==null&&Number.isFinite(p.x)&&Number.isFinite(p.y))current.push(p);else if(current.length){segments.push(current);current=[];}}if(current.length)segments.push(current);
    for(const segment of segments){if(s.kind==='band'){const valid=segment.filter(p=>Number.isFinite(p.lower)&&Number.isFinite(p.upper));if(valid.length)svg.append(svgElement('polygon',{points:[...valid.map(p=>`${X(p.x)},${Y(p.upper)}`),...valid.slice().reverse().map(p=>`${X(p.x)},${Y(p.lower)}`)].join(' '),class:'plot-band',fill:color,opacity:.16}));for(const p of valid){svg.append(svgElement('line',{x1:X(p.x),x2:X(p.x),y1:Y(p.lower),y2:Y(p.upper),class:'plot-whisker',stroke:color,opacity:.55,'stroke-width':1.5}));for(const y of [p.lower,p.upper])svg.append(svgElement('line',{x1:X(p.x)-4,x2:X(p.x)+4,y1:Y(y),y2:Y(y),class:'plot-whisker',stroke:color,opacity:.65,'stroke-width':1.5}));}}else if(s.kind!=='points'){svg.append(svgElement('polyline',{points:segment.map(p=>`${X(p.x)},${Y(p.y)}`).join(' '),class:'plot-line','data-tone':tone,fill:'none',stroke:color,'stroke-width':2.5,'stroke-linejoin':'round'}));}
      if(s.kind!=='band')for(const p of segment){const circle=svgElement('circle',{cx:X(p.x),cy:Y(p.y),r:s.kind==='points'?4.8:3.2,fill:color,tabindex:0});circle.append(svgElement('title',{},p.label?`${p.label} anchor: x=${number(p.x)} m, y=${number(p.y)} m`:`${s.name}: ${number(p.y)} at ${number(p.x)}${p.time!==undefined?`; t=${number(p.time)} s`:''}${p.lower!==undefined?`; local band ${number(p.lower)} to ${number(p.upper)}`:''}`));svg.append(circle);}
    }
  });card.append(svg);if(plot.help)card.append(node('p','plot-help',plot.help));return card;
}
function renderResult(result,job){
  state.result=result;$('empty-state').hidden=true;$('result-content').hidden=false;
  const diagnostics=result.diagnostics||[];const identity=result.identities||{};const verification=result.verification||{};
  $('result-state').textContent=job.mode==='replay'?'Replay complete':'Execution complete';
  $('metrics').replaceChildren();for(const [label,value,note] of [['Retained batches',String(diagnostics.length),'Updates and predictions'],['Reproduction',verification.outcome==='passed'?'Passed':'Inspect evidence','Same pinned providers'],['State admission','Not performed','Candidate estimates only']]){const metric=node('div','metric');metric.append(node('span','metric-label',label),node('span','metric-value',value),node('span','metric-note',note));$('metrics').append(metric);}
  $('plots').replaceChildren(...(result.plots||[]).map(renderPlot));$('diagnostics').replaceChildren();
  $('residuals').replaceChildren();for(const d of diagnostics){const tr=node('tr');for(const v of [number(d.time),d.status==='prediction_only'||d.status==='prediction-only'?'Prediction only':(d.status||'Updated').replaceAll('_',' '),String(d.channel_count??d.measurement_dimension??'—'),number(d.nis)])tr.append(node('td','',v));$('diagnostics').append(tr);for(const channel of d.channels||[]){const row=node('tr');for(const v of [number(d.time),channel.id,channel.unit,number(channel.innovation),number(channel.residual)])row.append(node('td','',v));$('residuals').append(row);}}
  $('residual-plots').replaceChildren(...(result.residual_plots||[]).map((plot,i)=>renderPlot(plot,100+i)));
  $('diagnostic-details').textContent=pretty(diagnostics);$('identities').replaceChildren();
  for(const [key,label] of [['evidence','Evidence'],['operation','Operation'],['execution','Execution'],['verification','Verification'],['bundle','Evidence bundle'],['numerical_result','Numerical result']]){const item=node('div','identity');item.append(node('span','identity-label',label),node('code','',Array.isArray(identity[key])?identity[key].join('\n'):identity[key]||'See evidence bundle'));$('identities').append(item);}
  $('verification-summary').textContent=verification.outcome==='passed'?'✓ Exact numerical reproduction passed · same providers · independent: false':'Inspect the retained verification details.';
  $('provenance').textContent=pretty({verification,authority:result.authority,providers:result.providers,replay_receipt:job.replay_receipt});
  $('evidence-export').disabled=false;$('config-export').disabled=false;$('replay').disabled=false;
}
async function pollJob(id,sequence){
  for(;;){if(sequence!==state.sequence)return;const job=await api('/api/runs/'+id);state.job=job;
    if(job.status==='succeeded'){if(job.mode!=='replay')state.original=job.id;renderResult(job.result,job);state.source=await api('/api/runs/'+job.id+'/configuration');$('source-preview').textContent=pretty(state.source);setStatus(job.mode==='replay'?'Replay passed. Fresh execution retained.':'Execution and numerical reproduction passed.','succeeded');
      $('replay-status').textContent=job.mode==='replay'?'Exact numerical output matched. Original: '+state.original.slice(0,12)+' · replay: '+job.id.slice(0,12):'Original execution retained for comparison.';return;}
    if(['failed','cancelled','timed_out'].includes(job.status)){const err=job.error||{};if(state.result)$('result-state').textContent='Retained result · latest attempt '+job.status.replaceAll('_',' ');if(job.status==='cancelled'){setStatus('Execution cancelled. Adjust your configuration and run again.');return;}throw new Error((err.message||`Execution ${job.status.replaceAll('_',' ')}.`)+(err.action?' '+err.action:''));}
    setStatus(job.status==='queued'?'Queued — waiting for an available worker.':'Running Python instruments and checking numerical reproduction…','running');await new Promise(resolve=>setTimeout(resolve,650));
  }
}
async function execute(replay=false){
  if(state.busy)return;if(!replay&&!$('configuration-form').reportValidity())return;clearError('run-error');setBusy(true);const seq=++state.sequence;
  if(state.result)$('result-state').textContent='Retained result · new execution in progress';
  try{const job=await api(replay?'/api/runs/'+state.original+'/replay':'/api/runs','POST',replay?{}:{example:state.example.id,parameters:params()});state.job=job;await pollJob(job.id,seq);}catch(error){showError('run-error',error);setStatus('Execution did not complete. See the action below.');}finally{if(seq===state.sequence)setBusy(false);}
}
async function download(type){try{const id=state.job?.status==='succeeded'?state.job.id:state.original;if(!id)throw new Error('Run an example before downloading its evidence.');const data=await api('/api/runs/'+id+'/'+type);const url=URL.createObjectURL(new Blob([pretty(data)+'\n'],{type:'application/json'}));const a=node('a');a.href=url;a.download=`net-${state.example.id}-${type}-${id.slice(0,12)}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(error){showError('run-error',error);}}
$('configuration-form').addEventListener('submit',event=>{event.preventDefault();execute();});$('reset').addEventListener('click',()=>selectExample(state.example));$('replay').addEventListener('click',()=>execute(true));
$('cancel').addEventListener('click',async()=>{if(!state.job)return;try{await api('/api/runs/'+state.job.id+'/cancel','POST');setStatus('Cancelling worker…','running');}catch(error){showError('run-error',error);}});
$('evidence-export').addEventListener('click',()=>download('evidence'));$('config-export').addEventListener('click',()=>download('configuration'));
$('parameters').addEventListener('input',()=>{if(state.result){$('result-state').textContent='Retained result · configuration changes pending';setStatus('Controls changed. Run again to produce a new result.');}});
async function initialize(){try{const data=await api('/api/catalog');state.csrf=data.csrf_token;state.catalog=data.examples||[];if(!state.catalog.length)throw new Error('No instruments passed startup qualification. Check the pinned provider installation and restart the service.');
  $('examples').replaceChildren();state.catalog.forEach((example,i)=>{const button=node('button','example');button.type='button';button.dataset.example=example.id;button.setAttribute('aria-pressed','false');button.append(node('span','number',String(i+1).padStart(2,'0')),node('span','name',example.name),node('span','brief',example.short_summary||example.summary));button.addEventListener('click',()=>selectExample(example));$('examples').append(button);});
  $('connection').textContent=`${state.catalog.length} instruments qualified`;$('connection').classList.add('ready');const limits=data.limits||{};$('run-help').textContent=`Synthetic observations · ${limits.wall_seconds||45}s execution limit · isolated Python workers`;selectExample(state.catalog[0]);
}catch(error){$('connection').textContent='Instruments unavailable';showError('startup-error',error);setStatus('Service unavailable. Reload after the installation issue is resolved.');}}
initialize();
