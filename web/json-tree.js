/* Collapsible JSON tree. window.jsonTreeHtml(value, label) -> html string;
   window.renderJsonTree(el, value, label). Uses native <details>/<summary>. */
(function (global) {
  "use strict";
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  function leaf(key, v) {
    var t = v === null ? "null" : typeof v;
    var shown = t === "string" ? '"' + v + '"' : String(v);
    return '<div class="jt-leaf"><span class="jt-key">' + esc(key) +
      '</span>: <span class="jt-val jt-' + t + '">' + esc(shown) + "</span></div>";
  }
  function node(key, v, depth) {
    if (v === null || typeof v !== "object") return leaf(key, v);
    var isArr = Array.isArray(v);
    var keys = isArr ? null : Object.keys(v);
    var len = isArr ? v.length : keys.length;
    if (!len) {
      return '<div class="jt-leaf"><span class="jt-key">' + esc(key) +
        '</span>: <span class="jt-val">' + (isArr ? "[]" : "{}") + "</span></div>";
    }
    var inner = "";
    if (isArr) {
      for (var i = 0; i < v.length; i++) inner += node(String(i), v[i], depth + 1);
    } else {
      keys.forEach(function (k) { inner += node(k, v[k], depth + 1); });
    }
    return '<details class="jt-node"' + (depth < 1 ? " open" : "") + ">" +
      '<summary><span class="jt-key">' + esc(key) + '</span> <span class="jt-meta">' +
      (isArr ? "[" + len + "]" : "{" + len + "}") + "</span></summary>" +
      '<div class="jt-children">' + inner + "</div></details>";
  }
  global.jsonTreeHtml = function (value, label) { return node(label || "data", value, 0); };
  global.renderJsonTree = function (el, value, label) {
    if (el) el.innerHTML = global.jsonTreeHtml(value, label);
  };
})(window);
