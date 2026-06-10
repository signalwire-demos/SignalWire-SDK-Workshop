/* Dependency-free coachmark/spotlight tour. No build step. */
(function (global) {
  "use strict";

  function el(tag, cls, html) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (html != null) n.innerHTML = html;
    return n;
  }

  function Tour(steps) {
    this.steps = steps || [];
    this.i = 0;
    this.overlay = null;
    this.tip = null;
    this._onResize = this.position.bind(this);
  }

  Tour.prototype.start = function () {
    if (!this.steps.length) return;
    this.i = 0;
    this.overlay = el("div", "tour-overlay");
    this.cut = el("div", "tour-cutout");
    this.tip = el("div", "tour-tip");
    this.overlay.appendChild(this.cut);
    document.body.appendChild(this.overlay);
    document.body.appendChild(this.tip);
    window.addEventListener("resize", this._onResize);
    var self = this;
    this._onKey = function (e) { if (e.key === "Escape") self.end(); };
    document.addEventListener("keydown", this._onKey);
    this.render();
  };

  Tour.prototype.target = function () {
    var s = this.steps[this.i];
    return s && document.querySelector(s.target);
  };

  Tour.prototype.render = function () {
    var s = this.steps[this.i];
    var t = this.target();
    if (!t) { this.next(); return; } // skip missing targets gracefully
    t.scrollIntoView({ behavior: "smooth", block: "center" });
    var last = this.i === this.steps.length - 1;
    this.tip.innerHTML =
      '<div class="tour-title">' + (s.title || "") + "</div>" +
      '<div class="tour-body">' + (s.body || "") + "</div>" +
      '<div class="tour-foot">' +
        '<span class="tour-count">' + (this.i + 1) + " / " + this.steps.length + "</span>" +
        '<span class="tour-btns">' +
          (this.i > 0 ? '<button data-act="back" class="tour-btn ghost">Back</button>' : "") +
          '<button data-act="skip" class="tour-btn ghost">Skip</button>' +
          '<button data-act="next" class="tour-btn">' + (last ? "Done" : "Next →") + "</button>" +
        "</span>" +
      "</div>";
    var self = this;
    this.tip.querySelectorAll("button").forEach(function (b) {
      b.onclick = function () {
        var a = b.getAttribute("data-act");
        if (a === "next") self.next();
        else if (a === "back") self.back();
        else self.end();
      };
    });
    // allow a quick beat for scroll before positioning
    setTimeout(this._onResize, 180);
  };

  Tour.prototype.position = function () {
    if (!this.overlay || !this.tip || !this.cut) return;
    var t = this.target();
    if (!t) return;
    var r = t.getBoundingClientRect();
    var pad = 8;
    this.cut.style.top = (r.top - pad) + "px";
    this.cut.style.left = (r.left - pad) + "px";
    this.cut.style.width = (r.width + pad * 2) + "px";
    this.cut.style.height = (r.height + pad * 2) + "px";
    var below = r.bottom + 12;
    var tipTop = (below + this.tip.offsetHeight > window.innerHeight)
      ? Math.max(12, r.top - this.tip.offsetHeight - 12)
      : below;
    this.tip.style.top = tipTop + "px";
    this.tip.style.left = Math.min(
      Math.max(12, r.left),
      window.innerWidth - this.tip.offsetWidth - 12
    ) + "px";
  };

  Tour.prototype.next = function () {
    if (this.i >= this.steps.length - 1) return this.end();
    this.i++; this.render();
  };
  Tour.prototype.back = function () { if (this.i > 0) { this.i--; this.render(); } };
  Tour.prototype.end = function () {
    window.removeEventListener("resize", this._onResize);
    if (this._onKey) document.removeEventListener("keydown", this._onKey);
    if (this.overlay) this.overlay.remove();
    if (this.tip) this.tip.remove();
    this.overlay = this.tip = null;
  };

  global.RoadshowTour = Tour;
})(window);
