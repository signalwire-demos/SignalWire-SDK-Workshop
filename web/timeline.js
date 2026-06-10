/* Timeline: phase bar + per-role swimlane. window.renderTimeline(el, timeline). */
(function (global) {
  "use strict";
  function esc(s){ return String(s==null?"":s).replace(/[&<>"]/g, function(c){
    return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]; }); }
  var PHASE_COLORS = { "Ring":"#044EF4", "Setup":"#601BE6", "AI Session":"#22c55e", "Teardown":"#FFD700" };
  var LANE_COLORS = { user:"#22c55e", assistant:"#044EF4", tool:"#FFD700", say:"#40E0D0" };

  global.renderTimeline = function (el, t) {
    if (!el) return;
    var phases = (t && t.phases) || [];
    var lanes = (t && t.lanes) || {};
    var b = (t && t.bounds) || {};
    if (!phases.length && !(lanes.assistant && lanes.assistant.length)) {
      el.innerHTML = '<p class="muted">No timeline for this call.</p>'; return;
    }
    // Phase bar
    var totalMs = phases.reduce(function(s,p){ return s + (p.ms||0); }, 0) || 1;
    var bar = phases.map(function(p){
      var pct = (p.ms/totalMs*100).toFixed(2);
      return '<div class="tl-phase" style="width:'+pct+'%;background:'+(PHASE_COLORS[p.name]||"#888")+'" title="'+esc(p.name)+' '+esc(p.ms/1000)+'s"></div>';
    }).join("");
    var legend = phases.map(function(p){
      return '<span class="tl-leg"><i style="background:'+(PHASE_COLORS[p.name]||"#888")+'"></i>'+esc(p.name)+' '+esc(p.ms/1000)+'s</span>';
    }).join("");
    // Swimlane (scale to AI bounds)
    var start = b.ai_start, end = b.ai_end, span = (start && end && end>start) ? (end-start) : 0;
    function seg(s){
      if (!span || !s.start) return "";
      var left = Math.max(0, (s.start - start)/span*100);
      var w = Math.max(0.6, ((Math.max(s.end||s.start, s.start) - s.start)/span*100));
      var tip = (s.text||s.name||"")+(s.latency?(" • "+s.latency+"ms"):"")+(s.confidence!=null?(" • "+Math.round(s.confidence*100)+"%"):"");
      return '<div class="tl-seg" style="left:'+left.toFixed(2)+'%;width:'+Math.min(w,100-left).toFixed(2)+'%" title="'+esc(tip)+'"></div>';
    }
    function lane(name, items){
      return '<div class="tl-lane"><div class="tl-lane-name">'+esc(name)+' ('+items.length+')</div>'+
        '<div class="tl-track" style="--c:'+(LANE_COLORS[name]||"#888")+'">'+items.map(seg).join("")+'</div></div>';
    }
    el.innerHTML =
      '<div class="tl-phasebar">'+bar+'</div><div class="tl-legend">'+legend+'</div>'+
      '<div class="tl-lanes">'+
        lane("user", lanes.user||[]) + lane("assistant", lanes.assistant||[]) +
        lane("tool", lanes.tool||[]) + lane("say", lanes.say||[]) +
      '</div>';
  };
})(window);
