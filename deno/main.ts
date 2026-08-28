// Прослойка с CORS-заголовками для Deno Deploy.
//
// Decky запрашивает список из браузерного контекста Steam с заголовком
// X-Decky-Version. Из-за нестандартного заголовка браузер сначала делает
// предварительный запрос OPTIONS, а статика (и GitHub Pages, и Netlify)
// отвечает на него 405 — список молча не загружается.
//
// Вариант на Netlify отвечает правильно, но соединение с ним рвётся на
// полпути: их логи показывают 200 и полный ответ, а на устройство он не
// доезжает. Поэтому тот же обработчик здесь — для домена, который на
// устройстве отвечает стабильно.
//
// Архивы плагинов сюда не идут: их качает питоновский бэкенд Decky напрямую с
// GitHub Pages, где CORS не применяется.

const MIRROR = "https://damilp320-spec.github.io/decky/plugins";

export function corsHeaders(request: Request): Headers {
  const headers = new Headers();
  const origin = request.headers.get("origin");
  // Эхо origin, а не звёздочка: так ответ подходит и для запросов с учётными
  // данными — официальный стор отвечает точно так же.
  headers.set("Access-Control-Allow-Origin", origin ?? "*");
  headers.set(
    "Access-Control-Allow-Headers",
    request.headers.get("access-control-request-headers") ?? "X-Decky-Version",
  );
  headers.set("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  if (origin) headers.set("Access-Control-Allow-Credentials", "true");
  headers.set("Access-Control-Max-Age", "600");
  headers.set("Vary", "Origin");
  return headers;
}

export async function handler(request: Request): Promise<Response> {
  const headers = corsHeaders(request);

  if (request.method === "OPTIONS") {
    return new Response(null, { status: 204, headers });
  }

  const path = new URL(request.url).pathname;

  if (path === "/") {
    headers.set("Content-Type", "text/html; charset=utf-8");
    return new Response(
      `<!doctype html><meta charset="utf-8"><title>Зеркало магазина Decky</title>` +
        `<p>Список плагинов — по адресу <code>/plugins</code>. ` +
        `Его вписывают в Decky → Settings → General → Store channel → Custom.`,
      { status: 200, headers },
    );
  }

  headers.set("Content-Type", "application/json; charset=utf-8");

  // Всё, что глубже /plugins — счётчик установок. Считать нечего, но без
  // ответа лоадер пишет ошибку в лог.
  if (path !== "/plugins") {
    return new Response(JSON.stringify({ ok: true }), { status: 200, headers });
  }

  try {
    const upstream = await fetch(MIRROR, { headers: { "User-Agent": "decky-mirror-cors" } });
    if (!upstream.ok) {
      return new Response(JSON.stringify({ error: `Зеркало ответило ${upstream.status}` }), {
        status: 502,
        headers,
      });
    }
    headers.set("Cache-Control", "public, max-age=300");
    return new Response(await upstream.text(), { status: 200, headers });
  } catch (error) {
    return new Response(JSON.stringify({ error: String(error) }), { status: 502, headers });
  }
}

// @ts-ignore: запускается только под Deno, в других средах модуль просто
// экспортирует обработчик для проверки.
if (typeof Deno !== "undefined") Deno.serve(handler);
