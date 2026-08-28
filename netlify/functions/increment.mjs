// Заглушка для счётчика установок (вариант для Netlify).
//
// После установки Decky шлёт POST на <адрес магазина>/<плагин>/versions/<версия>/increment.
// Считать установки зеркалу нечего, но без ответа лоадер пишет ошибку в лог,
// поэтому просто подтверждаем приём.

import { corsHeaders } from './plugins.mjs';

export default async function handler(req) {
  const headers = corsHeaders(req);

  if (req.method === 'OPTIONS') {
    return new Response(null, { status: 204, headers });
  }

  headers.set('Content-Type', 'application/json; charset=utf-8');
  return new Response(JSON.stringify({ ok: true }), { status: 200, headers });
}

export const config = { path: '/plugins/*' };
