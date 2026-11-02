// Small animations: count up numbers when the page loads
(function () {
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function countUp(el, target, suffix, after) {
    if (reduce) return;
    const start = performance.now();
    const duration = 1100;
    function tick(now) {
      const p = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - p, 3);
      el.textContent = Math.round(target * eased) + suffix + after;
      if (p < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }

  // Homepage stat numbers
  document.querySelectorAll("[data-count]").forEach(el => {
    countUp(el, parseInt(el.dataset.count, 10) || 0, el.dataset.suffix || "", "");
  });

  // Dashboard headline, e.g. "86% surviving"
  const big = document.querySelector(".headline .big");
  if (big) {
    const m = big.textContent.match(/^(\d+)%(.*)$/);
    if (m) countUp(big, parseInt(m[1], 10), "%", m[2]);
  }
})();
