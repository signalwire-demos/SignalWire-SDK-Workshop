/* Dashboard stat-card grid from a metrics object. window.renderDashboard(el, metrics). */
(function (global) {
  "use strict";
  function esc(s){ return String(s==null?"":s).replace(/[&<>"]/g, function(c){
    return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]; }); }
  function card(label, value, sub){
    return '<div class="m-card"><div class="m-label">'+esc(label)+'</div>'+
      '<div class="m-value">'+esc(value==null?"—":value)+'</div>'+
      (sub?'<div class="m-sub">'+esc(sub)+'</div>':'')+'</div>';
  }
  function section(title, cards){ return '<div class="m-section-title">'+esc(title)+'</div><div class="m-grid">'+cards.join("")+'</div>'; }
  function ms(v){ return v==null?null:v+" ms"; }
  function sec(v){ return v==null?null:v+"s"; }

  global.renderDashboard = function (el, m) {
    if (!el) return;
    if (!m || !m.conversation) { el.innerHTML = '<p class="muted">No metrics for this call.</p>'; return; }
    var d=m.durations||{}, la=(m.latency||{}).assistant, lt=(m.latency||{}).tool, c=m.conversation||{}, tk=m.tokens||{}, sw=m.swaig||{}, b=m.billing||{};
    var html = "";
    html += section("Duration", [
      card("Call", sec(d.call_total_s)), card("AI Session", sec(d.ai_session_s)),
      card("Ring", sec(d.ring_s)), card("Setup", sec(d.setup_s)), card("Teardown", sec(d.teardown_s)) ]);
    html += section("Assistant Latency", la ? [
      card("Average", ms(la.avg)), card("Median", ms(la.median)), card("P95", ms(la.p95)),
      card("Fastest", ms(la.fastest)), card("Slowest", ms(la.slowest)),
      card("Under 1200ms", (la.under_target||0)+" / "+la.count) ] : [card("Assistant Latency","—")]);
    html += '<div class="m-rating m-rating-'+esc((m.rating||"na").toLowerCase().replace(/\s+/g,"-"))+'">Rating: '+esc(m.rating||"N/A")+
      '<span class="m-sub"> (assistant responses only)</span></div>';
    if (lt) html += section("Tool Calls", [
      card("Average", ms(lt.avg)), card("Fastest", ms(lt.fastest)), card("Slowest", ms(lt.slowest)), card("Count", lt.count) ]);
    html += section("Conversation", [
      card("Turns", c.turns), card("User Messages", c.user_messages), card("Agent Responses", c.agent_responses),
      card("Total Words", c.total_words), card("Avg Response", c.avg_response_words!=null?c.avg_response_words+" words":null),
      card("ASR Confidence", c.asr_confidence_avg!=null?c.asr_confidence_avg+"%":null) ]);
    html += section("Tokens", [
      card("Input", tk.input), card("Output", tk.output), card("Avg TPS", tk.avg_tps), card("Peak TPS", tk.peak_tps) ]);
    html += section("SWAIG", [
      card("Total Calls", sw.total_calls), card("Avg Execution", ms(sw.avg_execution_ms)),
      card("Avg Function", ms(sw.avg_function_ms)), card("Action Types", sw.action_types),
      card("Functions", (sw.function_names||[]).join(", ")||"—") ]);
    html += section("Media & Billing", [
      card("TTS Chars", b.tts_chars), card("TTS Chars/min", b.tts_chars_per_min),
      card("ASR Minutes", b.asr_minutes), card("Total Minutes", b.total_minutes),
      card("Turns / min", b.call_rate_per_min!=null?b.call_rate_per_min+" /min":null) ]);
    el.innerHTML = html;
  };
})(window);
