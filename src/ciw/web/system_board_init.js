(() => {
  const NB=globalThis.NETBoard,$=NB.$;
  NB.renderClaims=()=>{
    const dl=NB.clear($("claims"));
    Object.entries(NB.board.claims).forEach(([key,value])=>NB.addPair(dl,key,value));
  };
  NB.render=()=>{
    NB.renderNavigation();
    NB.renderGraph();
    NB.renderInspector();
    NB.renderCandidate();
  };

  $("title").textContent=NB.board.title;
  $("board-id").textContent=NB.board.board_id;
  $("model-id").textContent=NB.board.model_id;
  $("board-digest").textContent=NB.short(NB.board.record_digest,45);
  $("edge-filter").value=NB.state.edgeFilter;

  $("edge-filter").addEventListener("change",event=>{
    NB.state.edgeFilter=event.target.value;
    NB.renderGraph();
  });
  $("back").addEventListener("click",NB.goUp);
  $("fit").addEventListener("click",()=>$("graph-scroll").scrollTo({left:0,top:0,behavior:"smooth"}));
  $("clear-edit").addEventListener("click",()=>{
    NB.state.staged=null;
    NB.render();
  });
  $("download-edit").addEventListener("click",NB.downloadEdit);

  NB.renderClaims();
  NB.render();
  document.body.dataset.ready="true";
})();
