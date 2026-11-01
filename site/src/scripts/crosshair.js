// Crosshair readout for TrendChart: snap to the nearest day and list the
// average and its band. A poll dot under the pointer wins over the line.
import { showTip, hideTip } from "./tooltip.js";

const fmt = (v, dl, rl) => (Math.abs(v) < 0.05 ? "Even" : `${v > 0 ? dl : rl}+${Math.abs(v).toFixed(1)}`);
const dateFmt = (iso) =>
  new Date(iso + "T12:00:00Z").toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });

for (const plot of document.querySelectorAll("[data-crosshair]")) {
  const data = JSON.parse(plot.dataset.crosshair);
  const line = plot.querySelector(".xhair");
  const n = data.d.length;
  plot.addEventListener("pointermove", (e) => {
    const dot = e.target.closest?.("[data-tip-value]");
    if (dot) {
      line.classList.remove("on");
      showTip(dot.dataset.tipValue, dot.dataset.tipLabel, e.clientX, e.clientY);
      return;
    }
    const r = plot.getBoundingClientRect();
    const f = Math.min(Math.max((e.clientX - r.left) / r.width, 0), 1);
    const i = Math.round(f * (n - 1));
    const [avg, lo, hi] = data.v[i];
    line.style.left = (i / (n - 1)) * 100 + "%";
    line.classList.add("on");
    showTip(
      `${fmt(avg, data.dl, data.rl)} on ${dateFmt(data.d[i])}`,
      `80% band ${fmt(lo, data.dl, data.rl)} to ${fmt(hi, data.dl, data.rl)}`,
      e.clientX,
      e.clientY,
    );
  });
  plot.addEventListener("pointerleave", () => {
    line.classList.remove("on");
    hideTip();
  });
}
