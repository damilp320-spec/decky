// Заглушка для счётчика установок.
//
// После установки Decky шлёт POST на <адрес магазина>/<плагин>/versions/<версия>/increment.
// Считать установки зеркалу нечего, но без ответа лоадер пишет ошибку в лог,
// поэтому просто подтверждаем приём.

export default function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', req.headers.origin || '*');
  res.setHeader('Access-Control-Allow-Headers', req.headers['access-control-request-headers'] || 'X-Decky-Version');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Vary', 'Origin');

  if (req.method === 'OPTIONS') {
    res.status(204).end();
    return;
  }
  res.status(200).json({ ok: true });
}
