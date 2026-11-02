// Weak signal handling: if a form can't reach the server, keep it on the phone
// and send it again as soon as the signal comes back.
const QUEUE_KEY = "saplingtrack-queue";

function readQueue() {
  try { return JSON.parse(localStorage.getItem(QUEUE_KEY)) || []; } catch (e) { return []; }
}
function writeQueue(q) {
  try { localStorage.setItem(QUEUE_KEY, JSON.stringify(q)); } catch (e) {}
}
function showBanner(on) {
  const b = document.getElementById("offline-banner");
  if (b) b.hidden = !on;
}

async function flushQueue() {
  const q = readQueue();
  if (!q.length) { showBanner(false); return; }
  const left = [];
  for (const item of q) {
    try {
      await fetch(item.url, { method: "POST", body: new URLSearchParams(item.data) });
    } catch (e) {
      left.push(item);
    }
  }
  writeQueue(left);
  showBanner(left.length > 0);
}

document.querySelectorAll("form[data-offline]").forEach(form => {
  form.addEventListener("submit", async event => {
    event.preventDefault();
    const url = form.action || window.location.href;
    const data = new FormData(form);
    try {
      const response = await fetch(url, { method: "POST", body: data });
      const html = await response.text();
      document.open(); document.write(html); document.close();
    } catch (e) {
      const q = readQueue();
      q.push({ url: url, data: Object.fromEntries(data) });
      writeQueue(q);
      showBanner(true);
    }
  });
});

window.addEventListener("online", flushQueue);
if (navigator.onLine) flushQueue(); else showBanner(readQueue().length > 0);
