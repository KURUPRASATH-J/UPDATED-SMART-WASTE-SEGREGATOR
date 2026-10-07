/* chart-theme.js — theme-aware colors for Chart.js charts.
   Reads the active theme's CSS custom properties at chart render time and
   re-applies them whenever the theme changes (`themechange` event, fired by
   theme-switcher.js), so legend labels, axis ticks and grid lines stay
   visible in every theme (dark, light, ocean, nature, sunset, galaxy).

   Plain classic script (no module exports) on purpose: pages load it in
   <head> so the inline chart-rendering functions can call ChartTheme
   synchronously before any module scripts run. */
(function () {
  var tracked = [];
  var hooked = false;

  /* Resolve the active theme tokens into concrete CSS color strings (canvas
     / Chart.js can't read `var(--x)` directly, so we resolve them). */
  function resolve() {
    var cs = getComputedStyle(document.body);
    function v(name, fb) {
      var s = (cs.getPropertyValue(name) || '').trim();
      return s || fb;
    }
    return {
      legend: v('--text-secondary', 'rgba(255,255,255,0.75)'),
      tick: v('--text-secondary', 'rgba(255,255,255,0.35)'),
      grid: v('--border-color', 'rgba(255,255,255,0.08)')
    };
  }

  /* Mutate a live Chart.js instance's options with the current tokens and
     re-render it. Safe to call on charts created with any option set. */
  function applyTo(chart) {
    if (!chart || typeof chart.options !== 'object') return;
    var c = resolve();
    var o = chart.options;
    if (o.plugins && o.plugins.legend && o.plugins.legend.labels) {
      o.plugins.legend.labels.color = c.legend;
    }
    if (o.scales) {
      ['y', 'y1', 'x', 'x1'].forEach(function (k) {
        var s = o.scales[k];
        if (!s) return;
        if (s.ticks) s.ticks.color = c.tick;
        if (s.grid) s.grid.color = c.grid;
      });
    }
    try {
      if (typeof chart.update === 'function') chart.update();
    } catch (e) { /* destroyed/resizing charts are fine to skip */ }
  }

  function untrack(chart) {
    var i = tracked.indexOf(chart);
    if (i !== -1) tracked.splice(i, 1);
  }

  function hook() {
    if (hooked) return;
    hooked = true;
    window.addEventListener('themechange', function () {
      tracked.forEach(function (ch) {
        try { applyTo(ch); } catch (e) {}
      });
    });
  }

  window.ChartTheme = {
    colors: resolve,
    applyTo: applyTo,
    track: function (chart) { if (chart && tracked.indexOf(chart) === -1) tracked.push(chart); hook(); },
    untrack: untrack
  };
})();