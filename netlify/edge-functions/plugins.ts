// Прослойка с CORS-заголовками, выполняется на CDN-слое Netlify.
//
// Decky запрашивает список из браузерного контекста Steam и шлёт свой заголовок
// X-Decky-Version. Из-за нестандартного заголовка браузер сначала делает
// предварительный запрос OPTIONS; GitHub Pages и статика Netlify отвечают на
// него 405, и список молча не загружается. Проверено на устройстве: запрос к
// эталонному серверу с правильными заголовками проходит, а к статике — падает
// с TypeError за полсекунды.
//
// Обычные функции Netlify тут не годятся: с некоторых сетей запрос за ними
// уходит вглубь облака и висит без ответа, тогда как edge отвечает с
// ближайшей точки — на устройстве она отзывается за 800 мс.
//
// Архивы плагинов сюда не идут: их качает питоновский бэкенд Decky напрямую с
// GitHub Pages, где CORS не применяется.

const MIRROR = Deno.env.get("MIRROR_URL") ?? "https://damilp320-spec.github.io/decky/plugins";

function corsHeaders(request: Request): Headers {
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

export default async function handler(request: Request): Promise<Response> {
  const headers = corsHeaders(request);

  if (request.method === "OPTIONS") {
    return new Response(null, { status: 204, headers });
  }

  headers.set("Content-Type", "application/json; charset=utf-8");

  // Всё, что глубже /plugins — счётчик установок. Считать нечего, но без
  // ответа лоадер пишет ошибку в лог.
  if (new URL(request.url).pathname !== "/plugins") {
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

export const config = { path: ["/plugins", "/plugins/*"] };
