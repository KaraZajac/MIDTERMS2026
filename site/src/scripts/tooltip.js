// One tooltip for the whole site. Any element with data-tip-value (and
// optionally data-tip-label) shows it on hover and on keyboard focus.
// Text goes in with textContent only: names come from scraped data.
const tip = document.createElement("div");
tip.className = "viz-tip";
tip.setAttribute("role", "status");
tip.hidden = true;
const valueEl = document.createElement("div");
valueEl.className = "viz-tip-value";
const labelEl = document.createElement("div");
labelEl.className = "viz-tip-label";
tip.append(valueEl, labelEl);
document.body.appendChild(tip);

function fill(el) {
  valueEl.textContent = el.dataset.tipValue || "";
  labelEl.textContent = el.dataset.tipLabel || "";
}
function place(x, y) {
  const pad = 14;
  tip.style.left = "0px";
  tip.style.top = "0px";
  const r = tip.getBoundingClientRect();
  let left = x + pad;
  let top = y + pad;
  if (left + r.width > innerWidth - 8) left = x - r.width - pad;
  if (top + r.height > innerHeight - 8) top = y - r.height - pad;
  tip.style.left = Math.max(8, left) + "px";
  tip.style.top = Math.max(8, top) + "px";
}
export function showTip(value, label, x, y) {
  valueEl.textContent = value;
  labelEl.textContent = label || "";
  tip.hidden = false;
  place(x, y);
}
export function hideTip() {
  tip.hidden = true;
}

document.addEventListener("pointermove", (e) => {
  if (e.target.closest?.("[data-crosshair], [data-cdf]")) return; // charts with their own readout
  const el = e.target.closest?.("[data-tip-value]");
  if (!el) {
    tip.hidden = true;
    return;
  }
  fill(el);
  tip.hidden = false;
  place(e.clientX, e.clientY);
});
document.addEventListener("pointerleave", () => (tip.hidden = true));
document.addEventListener("scroll", () => (tip.hidden = true), { passive: true });
document.addEventListener("focusin", (e) => {
  const el = e.target.closest?.("[data-tip-value]");
  if (!el) return;
  fill(el);
  tip.hidden = false;
  const r = el.getBoundingClientRect();
  place(r.left + r.width / 2, r.bottom);
});
document.addEventListener("focusout", () => (tip.hidden = true));
