// Minimal Phase 1 client. Intentionally bare — replace with a proper frontend.
const out = document.getElementById("out");

document.getElementById("uploadBtn").onclick = async () => {
  const f = document.getElementById("file").files[0];
  if (!f) return;
  const body = new FormData();
  body.append("file", f);
  const r = await fetch("/upload", { method: "POST", body });
  out.textContent = JSON.stringify(await r.json(), null, 2);
};

document.getElementById("askBtn").onclick = async () => {
  const q = document.getElementById("q").value;
  const r = await fetch(`/ask?question=${encodeURIComponent(q)}`, { method: "POST" });
  out.textContent = JSON.stringify(await r.json(), null, 2);
};
