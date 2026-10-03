(() => {
  const NB=globalThis.NETBoard,$=NB.$,html=NB.html;

  NB.addPair=(dl,key,value)=>{
    html("dt",{},dl,key);
    html("dd",{},dl,value===null||value===undefined||value===""?"—":String(value));
  };

  NB.renderGroupInspector=group=>{
    $("node-detail").classList.add("hide");
    $("group-detail").classList.remove("hide");
    $("selection-title").textContent=group.label;
    $("selection-subtitle").textContent="Hierarchical abstraction group";
    const dl=NB.clear($("group-fields"));
    NB.addPair(dl,"Group ID",group.group_id);
    NB.addPair(dl,"Level",NB.groupDepth(group.group_id));
    NB.addPair(dl,"Direct nodes",group.node_ids.length);
    NB.addPair(dl,"Child groups",NB.childGroups(group.group_id).length);
    NB.addPair(dl,"Nested nodes",NB.groupContainedNodeCount(group.group_id));
    $("enter-group").onclick=()=>NB.enterGroup(group.group_id);
  };

  NB.socketCard=(container,direction,socket)=>{
    const card=html("div",{class:"socket"},container);
    html("strong",{},card,direction.toUpperCase()+" / "+socket.socket_id);
    const port=socket.port;
    html("small",{},card,port.schema+" · unit "+(port.unit??"—")+" · frame "+(port.frame??"—")+" · scale "+(socket.scale.label||"—"));
    html("small",{},card,"uncertainty "+socket.uncertainty_semantics+" · provenance "+(socket.provenance_required?"required":"optional"));
  };

  NB.parseReplacement=(parameter,raw)=>{
    if(parameter.type==="NUMBER"){
      const value=Number(raw);
      if(!Number.isFinite(value)) throw new Error("Replacement must be a finite number");
      return value;
    }
    if(parameter.type==="INTEGER"){
      const value=Number(raw);
      if(!Number.isInteger(value)) throw new Error("Replacement must be an integer");
      return value;
    }
    if(parameter.type==="BOOLEAN") return raw==="true";
    return String(raw);
  };

  NB.validateClientDomain=(parameter,value)=>{
    const domain=parameter.domain;
    if(domain.kind==="FIXED"&&value!==parameter.value) throw new Error("FIXED parameter cannot be varied");
    if(domain.kind==="ENUM"&&!domain.values.some(candidate=>candidate===value)) throw new Error("Replacement is outside ENUM domain");
    if(domain.kind==="RANGE"||domain.kind==="LOG_RANGE"){
      if(Number(value)<domain.minimum||Number(value)>domain.maximum) throw new Error("Replacement is outside range");
      if(domain.kind==="LOG_RANGE"&&Number(value)<=0) throw new Error("LOG_RANGE replacement must be positive");
    }
  };

  NB.parameterCard=(container,node,name,parameter)=>{
    const card=html("div",{class:"param"},container),head=html("div",{class:"param-head"},card);
    html("span",{class:"param-name"},head,name);
    html("span",{class:"param-domain"},head,(parameter.exposed?parameter.domain.kind+" · exposed":parameter.domain.kind+" · internal"));
    const line=html("div",{class:"param-editor"},card);
    if(!parameter.exposed||parameter.domain.kind==="FIXED"){
      html("span",{class:"fixed"},line,String(parameter.value)+(parameter.unit?" "+parameter.unit:""));
      return;
    }
    let input;
    if(parameter.domain.kind==="ENUM"){
      input=html("select",{"aria-label":name+" replacement"},line);
      for(const candidate of parameter.domain.values){
        const option=html("option",{value:String(candidate)},input,String(candidate));
        if(candidate===parameter.value) option.selected=true;
      }
    }else if(parameter.type==="BOOLEAN"){
      input=html("select",{"aria-label":name+" replacement"},line);
      for(const candidate of [true,false]){
        const option=html("option",{value:String(candidate)},input,String(candidate));
        if(candidate===parameter.value) option.selected=true;
      }
    }else{
      input=html("input",{type:"number","aria-label":name+" replacement",value:String(parameter.value)},line);
      if(parameter.domain.minimum!==null) input.min=String(parameter.domain.minimum);
      if(parameter.domain.maximum!==null) input.max=String(parameter.domain.maximum);
      input.step=parameter.type==="INTEGER"?"1":"any";
    }
    const button=html("button",{type:"button"},line,"Stage");
    button.addEventListener("click",()=>{
      try{
        const replacement=NB.parseReplacement(parameter,input.value);
        NB.validateClientDomain(parameter,replacement);
        NB.stageEdit(node,name,parameter,replacement);
      }catch(error){
        $("candidate-empty").textContent=error.message;
        $("candidate-empty").classList.remove("hide");
        $("candidate-body").classList.add("hide");
      }
    });
  };

  NB.renderNodeInspector=node=>{
    $("group-detail").classList.add("hide");
    $("node-detail").classList.remove("hide");
    $("selection-title").textContent=node.label;
    $("selection-subtitle").textContent=node.kind+" · "+node.node_id;
    const fields=NB.clear($("node-fields"));
    NB.addPair(fields,"Kind",node.kind);
    NB.addPair(fields,"Capability",node.semantic_capability);
    NB.addPair(fields,"Scale",node.scale.label||"—");
    NB.addPair(fields,"Resources",node.resources.join(", ")||"—");
    NB.addPair(fields,"Authority",node.authority_requirements.join(", ")||"—");
    NB.addPair(fields,"Provenance refs",node.provenance_refs.length);

    const sockets=NB.clear($("socket-list"));
    if(!node.sockets.inputs.length&&!node.sockets.outputs.length){
      html("div",{class:"empty"},sockets,"No typed sockets declared.");
    }else{
      node.sockets.inputs.forEach(socket=>NB.socketCard(sockets,"input",socket));
      node.sockets.outputs.forEach(socket=>NB.socketCard(sockets,"output",socket));
    }

    const params=NB.clear($("parameter-list")),names=Object.keys(node.parameters);
    if(!names.length) html("div",{class:"empty"},params,"No parameters declared.");
    names.forEach(name=>NB.parameterCard(params,node,name,node.parameters[name]));

    const contracts=NB.clear($("contract-list"));
    let any=false;
    for(const [label,values] of [["Invariant",node.invariants],["Validity",node.validity_conditions]]){
      for(const value of values){
        any=true;
        html("div",{class:"contract-row"},contracts,label+": "+value);
      }
    }
    if(!any) html("div",{class:"empty"},contracts,"No node invariants or validity conditions declared.");
  };

  NB.renderInspector=()=>{
    if(!NB.state.selected){
      $("selection-title").textContent="Nothing selected";
      $("selection-subtitle").textContent="Select a node or group.";
      $("group-detail").classList.add("hide");
      $("node-detail").classList.add("hide");
      return;
    }
    if(NB.state.selected.type==="group") NB.renderGroupInspector(NB.groupMap.get(NB.state.selected.id));
    else NB.renderNodeInspector(NB.nodeMap.get(NB.state.selected.id));
  };

  NB.simpleHash=value=>{
    const source=JSON.stringify(value);
    let hash=2166136261;
    for(let i=0;i<source.length;i+=1){
      hash^=source.charCodeAt(i);
      hash=Math.imul(hash,16777619);
    }
    return (hash>>>0).toString(16).padStart(8,"0");
  };

  NB.stageEdit=(node,name,parameter,replacement)=>{
    const closure=NB.dependencyClosure(node.node_id);
    const editId=("visual-"+node.node_id+"-"+name+"-"+NB.simpleHash(replacement))
      .replace(/[^A-Za-z0-9_.-]/g,"_").slice(0,120);
    NB.state.staged={
      editId,
      target:{node_id:node.node_id,parameter:name},
      before:parameter.value,
      replacement,
      closure
    };
    NB.render();
  };

  NB.renderCandidate=()=>{
    if(!NB.state.staged){
      $("candidate-empty").textContent="Choose an exposed parameter and stage a replacement.";
      $("candidate-empty").classList.remove("hide");
      $("candidate-body").classList.add("hide");
      $("clear-edit").disabled=true;
      $("staged-status").textContent="NONE";
      return;
    }
    $("candidate-empty").classList.add("hide");
    $("candidate-body").classList.remove("hide");
    $("clear-edit").disabled=false;
    $("staged-status").textContent="1 EDIT";
    $("candidate-target").textContent=NB.state.staged.target.node_id+"."+NB.state.staged.target.parameter;
    $("candidate-before").textContent=String(NB.state.staged.before);
    $("candidate-after").textContent=String(NB.state.staged.replacement);
    $("candidate-closure").textContent=NB.state.staged.closure.length+" nodes · "+NB.state.staged.closure.join(", ");
  };

  NB.editSpec=()=>{
    if(!NB.state.staged) return null;
    return {
      schema:"ciw.board-visual-edit-spec.v1",
      edit_id:NB.state.staged.editId,
      board_ref:NB.board.record_digest,
      target:{...NB.state.staged.target},
      replacement:NB.state.staged.replacement,
      notes:"Generated by the local NET System Board visual editor. Candidate only; no execution or acceptance performed."
    };
  };

  NB.downloadEdit=()=>{
    const spec=NB.editSpec();
    if(!spec) return;
    const blob=new Blob([JSON.stringify(spec,null,2)+"\n"],{type:"application/json"});
    const url=URL.createObjectURL(blob),anchor=document.createElement("a");
    anchor.href=url;
    anchor.download=spec.edit_id+".json";
    anchor.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
  };
})();
