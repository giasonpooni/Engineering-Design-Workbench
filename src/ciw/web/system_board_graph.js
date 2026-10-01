(() => {
  const NB=globalThis.NETBoard,$=NB.$,svg=NB.svg;
  NB.drawCard=(layer,item,pos)=>{
    const key=item.type+":"+item.id;
    const selected=NB.state.selected&&(NB.state.selected.type+":"+NB.state.selected.id===key);
    const affectedSet=new Set(NB.state.staged?NB.state.staged.closure:[]);
    let affected=false,target=false;
    if(item.type==="node"){
      affected=affectedSet.has(item.id);
      target=!!NB.state.staged&&NB.state.staged.target.node_id===item.id;
    }else if(item.type==="group"&&NB.state.staged){
      affected=NB.state.staged.closure.some(nodeId=>{
        const member=NB.membership.get(nodeId)??null;
        return member!==null&&NB.isDescendantGroup(member,item.id);
      });
    }
    const classes=[
      item.type==="group"?"node-card group-card":"node-card",
      selected?"selected":"",affected?"affected":"",target?"target":""
    ].filter(Boolean).join(" ");
    const g=svg("g",{
      class:classes,transform:"translate("+pos.x+","+pos.y+")",tabindex:"0",role:"button",
      "aria-label":item.type==="group"?"Open group "+item.raw.label:"Inspect "+item.raw.label
    },layer);
    svg("rect",{x:0,y:0,rx:7,width:220,height:110},g);
    if(item.type==="group"){
      svg("path",{d:"M 15 16 L 21 22 L 15 28 L 9 22 Z",class:"group-diamond"},g);
      svg("text",{x:30,y:25,class:"node-title"},g,NB.short(item.raw.label,27));
      svg("text",{x:14,y:50,class:"node-meta"},g,"GROUP · level "+NB.groupDepth(item.id));
      svg("text",{x:14,y:68,class:"node-meta"},g,NB.groupContainedNodeCount(item.id)+" nested nodes");
      svg("text",{x:14,y:90,class:"node-meta"},g,"enter →");
    }else{
      svg("circle",{cx:15,cy:21,r:5,class:"node-kind-dot "+item.raw.kind},g);
      svg("text",{x:28,y:25,class:"node-title"},g,NB.short(item.raw.label,28));
      svg("text",{x:14,y:49,class:"node-meta"},g,item.raw.kind+" · "+(item.raw.scale.label||"scale n/a"));
      const exposed=Object.values(item.raw.parameters).filter(p=>p.exposed).length;
      svg("text",{x:14,y:67,class:"node-meta"},g,Object.keys(item.raw.parameters).length+" params · "+exposed+" exposed");
      svg("text",{x:14,y:86,class:"node-meta"},g,item.raw.semantic_capability?NB.short(item.raw.semantic_capability,31):"descriptive / non-operation");
      if(affected) svg("text",{x:206,y:100,"text-anchor":"end",class:"node-meta"},g,target?"TARGET":"AFFECTED");
    }
    const activate=()=>{NB.state.selected={type:item.type,id:item.id};NB.render();};
    g.addEventListener("click",activate);
    g.addEventListener("dblclick",()=>{if(item.type==="group") NB.enterGroup(item.id);});
    g.addEventListener("keydown",event=>{
      if(event.key==="Enter"||event.key===" "){
        event.preventDefault();
        if(item.type==="group"&&event.key==="Enter") NB.enterGroup(item.id); else activate();
      }
    });
  };

  NB.renderGraph=()=>{
    const canvas=NB.clear($("board-svg")),items=NB.visibleItems(),edges=NB.projectedEdges(items);
    const depth=NB.executionDepths(items,edges),buckets=new Map();
    for(const item of items){
      const key=item.type+":"+item.id,d=depth.get(key)??0;
      if(!buckets.has(d)) buckets.set(d,[]);
      buckets.get(d).push(item);
    }
    for(const rows of buckets.values()) rows.sort((a,b)=>a.raw.label.localeCompare(b.raw.label));
    const depths=[...buckets.keys()],rowCounts=[...buckets.values()].map(rows=>rows.length);
    const maxDepth=depths.length?Math.max(...depths):0,maxRows=rowCounts.length?Math.max(...rowCounts):1;
    const width=Math.max(820,90+(maxDepth+1)*290),height=Math.max(480,80+maxRows*155);
    canvas.setAttribute("viewBox","0 0 "+width+" "+height);
    canvas.setAttribute("width",String(width));canvas.setAttribute("height",String(height));
    const defs=svg("defs",{},canvas),marker=svg("marker",{
      id:"arrow",viewBox:"0 0 10 10",refX:9,refY:5,markerWidth:7,markerHeight:7,orient:"auto-start-reverse"
    },defs);
    svg("path",{d:"M 0 0 L 10 5 L 0 10 z",fill:"#52677e"},marker);
    const positions=new Map();
    [...buckets.entries()].sort((a,b)=>a[0]-b[0]).forEach(([d,rows])=>{
      rows.forEach((item,index)=>positions.set(item.type+":"+item.id,{x:45+d*290,y:45+index*155}));
    });
    const edgeLayer=svg("g",{"aria-label":"relations"},canvas);
    for(const edge of edges){
      const a=positions.get(edge.source),b=positions.get(edge.target);if(!a||!b) continue;
      const x1=a.x+220,y1=a.y+55,x2=b.x,y2=b.y+55,bend=Math.max(42,(x2-x1)*0.45);
      const path="M "+x1+" "+y1+" C "+(x1+bend)+" "+y1+", "+(x2-bend)+" "+y2+", "+x2+" "+y2;
      svg("path",{d:path,class:"edge "+edge.kind,"marker-end":"url(#arrow)"},edgeLayer);
      const label=edge.count>1?edge.kind+" ×"+edge.count:edge.kind;
      svg("text",{x:(x1+x2)/2,y:(y1+y2)/2-6,class:"edge-label","text-anchor":"middle"},edgeLayer,label);
    }
    const nodeLayer=svg("g",{"aria-label":"nodes and groups"},canvas);
    for(const item of items) NB.drawCard(nodeLayer,item,positions.get(item.type+":"+item.id));
    $("visible-count").textContent=String(items.length);
    $("edge-count").textContent=String(edges.length);
    $("level").textContent=String(NB.state.scope===null?0:NB.groupDepth(NB.state.scope));
    $("scope-title").textContent=NB.state.scope===null?NB.board.title:NB.groupMap.get(NB.state.scope).label;
    $("back").disabled=NB.state.scope===NB.initialScope||(NB.state.scope===null&&NB.initialScope===null);
  };

  NB.enterGroup=groupId=>{
    if(!NB.groupMap.has(groupId)) return;
    NB.state.scope=groupId;NB.state.selected=null;NB.render();
    $("graph-scroll").scrollTo({left:0,top:0});
  };
  NB.goUp=()=>{
    if(NB.state.scope===NB.initialScope||NB.state.scope===null) return;
    const group=NB.groupMap.get(NB.state.scope),parent=group.parent_group_id;
    NB.state.scope=parent===null&&NB.initialScope!==null?NB.initialScope:parent;
    NB.state.selected={type:"group",id:group.group_id};NB.render();
  };
  NB.renderNavigation=()=>{
    const crumbs=["Board",...NB.scopePath(NB.state.scope).map(group=>group.label)];
    $("breadcrumb").textContent=crumbs.join(" / ");
  };
})();
