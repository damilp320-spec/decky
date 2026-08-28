// Отдаёт список плагинов с зеркала, добавляя CORS-заголовки.
//
// Decky запрашивает список из браузерного контекста Steam и шлёт свой
// заголовок X-Decky-Version. Из-за нестандартного заголовка браузер сначала
// делает preflight-запрос OPTIONS, а GitHub Pages на него отвечает 405 без
// CORS-заголовков — список молча не загружается. Эта функция проксирует тот
// же JSON и отвечает так, как ожидает браузер.
//
// Архивы плагинов сюда не идут: их качает питоновский бэкенд Decky напрямую с
// GitHub Pages, и CORS там не применяется.

const MIRROR = process.env.MIRROR_URL || 'https://damilp320-spec.github.io/decky/plugins';

function setCors(req, res) {
  res.setHeader('Access-Control-Allow-Origin', req.headers.origin || '*');
  // Эхо запрошенных заголовков надёжнее звёздочки: работает и с credentials.
  res.setHeader('Access-Control-Allow-Headers', req.headers['access-control-request-headers'] || 'X-Decky-Version');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Max-Age', '600');
  res.setHeader('Vary', 'Origin');
}

export default async function handler(req, res) {
  setCors(req, res);

  if (req.method === 'OPTIONS') {
    res.status(204).end();
    return;
  }

  try {
    const upstream = await fetch(MIRROR, { headers: { 'User-Agent': 'decky-mirror-cors' } });
    if (!upstream.ok) {
      res.status(502).json({ error: `Зеркало ответило ${upstream.status}` });
      return;
    }
    const body = await upstream.text();
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.setHeader('Cache-Control', 'public, max-age=300, s-maxage=300');
    res.status(200).send(body);
  } catch (error) {
    res.status(502).json({ error: String(error) });
  }
}
