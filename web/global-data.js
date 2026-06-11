/* Global Data snapshot — one card per captured section, each a JSON tree.
   window.renderGlobalData(el, gd). Requires json-tree.js (jsonTreeHtml). */
(function (global) {
  "use strict";
  var TITLES = [
    ["global_data", "Global Data"],
    ["user_variables", "User Variables"],
    ["swml_vars", "SWML Variables"],
    ["call_metadata", "Call Metadata"],
    ["params", "Parameters"],
    ["prompt_vars", "Prompt Variables"],
    ["previous_contexts", "Previous Contexts"]
  ];
  global.renderGlobalData = function (el, gd) {
    if (!el) return;
    var html = "";
    TITLES.forEach(function (t) {
      var key = t[0], title = t[1];
      if (!gd || gd[key] === undefined) return;
      html += '<div class="m-section-title">' + title + "</div>" +
        '<div class="tool-card">' +
        (global.jsonTreeHtml ? global.jsonTreeHtml(gd[key], key) :
          "<pre>" + JSON.stringify(gd[key], null, 2).replace(/</g, "\\u003c") + "</pre>") +
        "</div>";
    });
    el.innerHTML = html || '<p class="muted">No global data captured for this call.</p>';
  };
})(window);
