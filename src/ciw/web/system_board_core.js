"use strict";
(() => {
  const NB = globalThis.NETBoard = {};
  const encoded = document.getElementById("net-board").textContent.trim();
  const bytes = Uint8Array.from(atob(encoded), c => c.charCodeAt(0));
  NB.board = JSON.parse(new TextDecoder("utf-8", {fatal:true}).decode(bytes));
  const freeze = value => {
    if (value && typeof value === "object") {
      Object.values(value).forEach(freeze);
      Object.freeze(value);
    }
    return value;
  };
  freeze(NB.board);
  NB.$ = id => document.getElementById(id);
  NB.NS = "http://www.w3.org/2000/svg";
  NB.nodeMap = new Map(NB.board.nodes.map(node => [node.node_id,node]));
  NB.groupMap = new Map(NB.board.groups.map(group => [group.group_id,group]));
  NB.membership = new Map();
  NB.board.groups.forEach(group => group.node_ids.forEach(id => NB.membership.set(id,group.group_id)));
  const topGroups = NB.board.groups.filter(group => group.parent_group_id === null);
  const topUngrouped = NB.board.nodes.filter(node => !NB.membership.has(node.node_id));
  NB.initialScope = topGroups.length === 1 && topUngrouped.length === 0 && topGroups[0].node_ids.length === 0
    ? topGroups[0].group_id : null;
  NB.state = {scope:NB.initialScope,edgeFilter:"EXECUTION",selected:null,staged:null};

  NB.svg = (tag,attrs={},parent=null,text=null) => {
    const el=document.createElementNS(NB.NS,tag);
    Object.entries(attrs).forEach(([key,value])=>el.setAttribute(key,String(value)));
    if(text!==null) el.textContent=String(text);
    if(parent) parent.appendChild(el);
    return el;
  };
  NB.html = (tag,attrs={},parent=null,text=null) => {
    const el=document.createElement(tag);
    Object.entries(attrs).forEach(([key,value])=>{
      if(key==="class") el.className=value; else el.setAttribute(key,String(value));
    });
    if(text!==null) el.textContent=String(text);
    if(parent) parent.appendChild(el);
    return el;
  };
  NB.clear = el => {el.replaceChildren();return el;};
  NB.short = (value,limit=32) => {
    const text=String(value);
    return text.length>limit ? text.slice(0,limit-8)+"…"+text.slice(-7) : text;
  };
  NB.groupDepth = groupId => {
    if(groupId===null) return 0;
    let depth=0,current=NB.groupMap.get(groupId);
    const seen=new Set();
    while(current && current.parent_group_id!==null){
      if(seen.has(current.group_id)) break;
      seen.add(current.group_id);depth+=1;
      current=NB.groupMap.get(current.parent_group_id);
    }
    return depth;
  };
  NB.childGroups = scope => NB.board.groups.filter(group=>group.parent_group_id===scope);
  NB.directNodes = scope => scope===null
    ? NB.board.nodes.filter(node=>!NB.membership.has(node.node_id))
    : NB.board.nodes.filter(node=>NB.membership.get(node.node_id)===scope);
  NB.isDescendantGroup = (groupId,ancestorId) => {
    if(groupId===null) return ancestorId===null;
    let current=NB.groupMap.get(groupId);
    const seen=new Set();
    while(current){
      if(current.group_id===ancestorId) return true;
      if(seen.has(current.group_id)||current.parent_group_id===null) break;
      seen.add(current.group_id);current=NB.groupMap.get(current.parent_group_id);
    }
    return ancestorId===null;
  };
  NB.visibleOwner = (nodeId,scope) => {
    const member=NB.membership.get(nodeId)??null;
    if(scope===null){
      if(member===null) return "node:"+nodeId;
      let current=NB.groupMap.get(member);
      while(current&&current.parent_group_id!==null) current=NB.groupMap.get(current.parent_group_id);
      return current ? "group:"+current.group_id : null;
    }
    if(member===scope) return "node:"+nodeId;
    if(member===null||!NB.isDescendantGroup(member,scope)) return null;
    let current=NB.groupMap.get(member);
    while(current&&current.parent_group_id!==scope){
      if(current.parent_group_id===null) return null;
      current=NB.groupMap.get(current.parent_group_id);
    }
    return current ? "group:"+current.group_id : null;
  };
  NB.visibleItems = () => [
    ...NB.childGroups(NB.state.scope).map(group=>({type:"group",id:group.group_id,raw:group})),
    ...NB.directNodes(NB.state.scope).map(node=>({type:"node",id:node.node_id,raw:node}))
  ];
  NB.edgeAllowed = edge => {
    if(NB.state.edgeFilter==="ALL") return true;
    if(NB.state.edgeFilter==="EXECUTION") return edge.kind==="DATAFLOW"||edge.kind==="DEPENDENCY";
    return edge.kind===NB.state.edgeFilter;
  };
  NB.projectedEdges = items => {
    const allowed=new Set(items.map(item=>item.type+":"+item.id));
    const merged=new Map();
    for(const edge of NB.board.edges){
      if(!NB.edgeAllowed(edge)) continue;
      const source=NB.visibleOwner(edge.source_node_id,NB.state.scope);
      const target=NB.visibleOwner(edge.target_node_id,NB.state.scope);
      if(!source||!target||source===target||!allowed.has(source)||!allowed.has(target)) continue;
      const key=source+"|"+target+"|"+edge.kind;
      if(!merged.has(key)) merged.set(key,{source,target,kind:edge.kind,count:0,relations:new Set()});
      const row=merged.get(key);row.count+=1;row.relations.add(edge.relation);
    }
    return [...merged.values()].map(row=>({...row,relations:[...row.relations]}));
  };
  NB.executionDepths = (items,edges) => {
    const ids=items.map(item=>item.type+":"+item.id);
    const depth=new Map(ids.map(id=>[id,0]));
    const exec=edges.filter(edge=>edge.kind==="DATAFLOW"||edge.kind==="DEPENDENCY");
    for(let pass=0;pass<ids.length;pass+=1){
      let changed=false;
      for(const edge of exec){
        const candidate=(depth.get(edge.source)??0)+1;
        if(candidate>(depth.get(edge.target)??0)&&candidate<=ids.length){
          depth.set(edge.target,candidate);changed=true;
        }
      }
      if(!changed) break;
    }
    return depth;
  };
  NB.groupContainedNodeCount = groupId => NB.board.nodes.filter(node=>{
    const member=NB.membership.get(node.node_id)??null;
    return member!==null&&NB.isDescendantGroup(member,groupId);
  }).length;
  NB.dependencyClosure = nodeId => {
    const outgoing=new Map(NB.board.nodes.map(node=>[node.node_id,[]]));
    for(const edge of NB.board.edges){
      if(edge.kind!=="DATAFLOW"&&edge.kind!=="DEPENDENCY") continue;
      if(!outgoing.has(edge.source_node_id)) outgoing.set(edge.source_node_id,[]);
      outgoing.get(edge.source_node_id).push(edge.target_node_id);
    }
    const seen=new Set([nodeId]),queue=[nodeId];
    while(queue.length){
      const current=queue.shift();
      for(const next of outgoing.get(current)??[]){
        if(!seen.has(next)){seen.add(next);queue.push(next);}
      }
    }
    return [...seen];
  };
  NB.scopePath = scope => {
    if(scope===null) return [];
    const path=[],seen=new Set();let current=NB.groupMap.get(scope);
    while(current&&!seen.has(current.group_id)){
      path.unshift(current);seen.add(current.group_id);
      current=current.parent_group_id===null?null:NB.groupMap.get(current.parent_group_id);
    }
    return path;
  };
})();
