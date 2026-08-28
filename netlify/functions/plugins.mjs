// Отдаёт список плагинов с зеркала, добавляя CORS-заголовки (вариант для Netlify).
//
// Decky запрашивает список из браузерного контекста Steam и шлёт свой заголовок
// X-Decky-Version. Из-за нестандартного заголовка браузер сначала делает
// preflight-запрос OPTIONS, а GitHub Pages отвечает на него 405 без
// CORS-заголовков — список молча не загружается.
//
// Архивы плагинов сюда не идут: их качает питоновский бэкенд Decky напрямую с
// GitHub Pages, и CORS там не применяется.

const MIRROR = process.env.MIRROR_URL || 'https://damilp320-spec.github.io/decky/plugins';

export function corsHeaders(req) {
  const headers = new Headers();
  headers.set('Access-Control-Allow-Origin', req.headers.get('origin') || '*');
  // Эхо запрошенных заголовков надёжнее звёздочки: работает и с credentials.
  headers.set(
    'Access-Control-Allow-Headers',
    req.headers.get('access-control-request-headers') || 'X-Decky-Version',
  );
  headers.set('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  headers.set('Access-Control-Max-Age', '600');
  headers.set('Vary', 'Origin');
  return headers;
}

export default async function handler(req) {
  const headers = corsHeaders(req);

  if (req.method === 'OPTIONS') {
    return new Response(null, { status: 204, headers });
  }

  try {
    const upstream = await fetch(MIRROR, { headers: { 'User-Agent': 'decky-mirror-cors' } });
    if (!upstream.ok) {
      headers.set('Content-Type', 'application/json; charset=utf-8');
      return new Response(JSON.stringify({ error: `Зеркало ответило ${upstream.status}` }), {
        status: 502,
        headers,
      });
    }
    headers.set('Content-Type', 'application/json; charset=utf-8');
    headers.set('Cache-Control', 'public, max-age=300');
    return new Response(await upstream.text(), { status: 200, headers });
  } catch (error) {
    headers.set('Content-Type', 'application/json; charset=utf-8');
    return new Response(JSON.stringify({ error: String(error) }), { status: 502, headers });
  }
}

export const config = { path: '/plugins' };
