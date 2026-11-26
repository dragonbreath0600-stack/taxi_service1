function esc(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML.replace(/"/g, "&quot;");
}

function toast(text) {
  const div = document.createElement("div");
  div.className = "toast";
  div.textContent = text;
  document.body.append(div);
  setTimeout(() => div.remove(), 4000);
}

function logout() {
  localStorage.removeItem("token");
  location.replace("index.html");
}

async function api(path, method = "GET", body, auth = true) {
  const headers = { "Content-Type": "application/json" };
  if (auth) headers.Authorization = "Bearer " + localStorage.getItem("token");
  const response = await fetch(path, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (response.status === 401 && auth) {
    logout();
    throw new Error("Требуется вход");
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(typeof data.detail === "string" ? data.detail : "Проверьте введённые данные");
  }
  return data;
}

function openPage(role) {
  location.replace(role === "driver" ? "driver.html" : "passenger.html");
}

async function startPage(role, handlers, reload) {
  const me = await api("/api/me");
  if (me.role !== role) return openPage(me.role);
  document.getElementById("username").textContent = me.username;
  await reload();
  const source = new EventSource("/api/events?token=" + localStorage.getItem("token"));
  source.onopen = reload;
  source.onerror = () => api("/api/me").catch(() => {});
  for (const name in handlers) {
    source.addEventListener(name, (event) => handlers[name](JSON.parse(event.data)));
  }
}
