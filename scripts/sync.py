#!/usr/bin/env python3
"""Собирает зеркало магазина плагинов Decky для раздачи через GitHub.

Скрипт ходит на официальный стор (plugins.deckbrew.xyz), скачивает zip-архивы
плагинов и картинки, проверяет SHA-256 (Decky обязательно сверяет хеш при
установке) и складывает всё в каталог dist/ вместе с переписанным JSON.

В JSON у каждой версии проставляется поле "artifact" — Decky качает архив
именно по нему, если оно есть (см. frontend/src/store.tsx в decky-loader).
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import html
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zipfile import ZipFile

SOURCE_STORE = os.environ.get("SOURCE_STORE", "https://plugins.deckbrew.xyz/plugins")
PAGES_BASE = os.environ.get("PAGES_BASE", "").rstrip("/")
RELEASE_BASE = os.environ.get("RELEASE_BASE", "").rstrip("/")
KEEP_VERSIONS = int(os.environ.get("KEEP_VERSIONS", "1"))
DIST = Path(os.environ.get("DIST", "dist"))
CACHE_DIR = Path(os.environ.get("CACHE_DIR", ".cache/artifacts"))
# Хардлимит GitHub Pages на файл — 100 МБ, оставляем запас.
MAX_PAGES_FILE_BYTES = int(os.environ.get("MAX_PAGES_FILE_MB", "95")) * 1024 * 1024
WORKERS = int(os.environ.get("WORKERS", "8"))

USER_AGENT = "decky-github-mirror (+https://github.com/%s)" % os.environ.get(
    "GITHUB_REPOSITORY", "local"
)


def http_get(url: str, retries: int = 4, timeout: int = 180) -> bytes:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as exc:  # сеть, 5xx, обрыв — пробуем ещё раз
            last = exc
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"не удалось скачать {url}: {last}")


def artifact_source(hash_: str) -> str:
    return f"https://cdn.tzatzikiweeb.moe/file/steam-deck-homebrew/versions/{hash_}.zip"


def fetch_artifact(hash_: str) -> Path:
    """Возвращает путь к zip с нужным хешем, скачивая его при необходимости."""
    cached = CACHE_DIR / f"{hash_}.zip"
    if cached.is_file() and sha256_file(cached) == hash_:
        return cached
    data = http_get(artifact_source(hash_))
    got = hashlib.sha256(data).hexdigest()
    if got != hash_:
        raise RuntimeError(f"SHA-256 не совпал: ожидали {hash_}, получили {got}")
    cached.parent.mkdir(parents=True, exist_ok=True)
    tmp = cached.with_suffix(".part")
    tmp.write_bytes(data)
    tmp.replace(cached)
    return cached


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def remote_binary_hosts(zip_path: Path) -> list[str]:
    """Плагины могут докачивать бинарники со сторонних адресов при установке."""
    hosts: set[str] = set()
    try:
        with ZipFile(zip_path) as archive:
            for name in archive.namelist():
                if name.count("/") == 1 and name.endswith("/package.json"):
                    meta = json.loads(archive.read(name).decode("utf-8"))
                    for binary in meta.get("remote_binary") or []:
                        url = binary.get("url", "")
                        if "://" in url:
                            hosts.add(url.split("/")[2])
    except Exception:
        pass
    return sorted(hosts)


def mirror_image(url: str) -> str | None:
    """Кладёт картинку в dist/images и возвращает её имя файла."""
    if not url:
        return None
    ext = os.path.splitext(url.split("?")[0])[1].lower()
    if ext not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        ext = ".png"
    name = hashlib.sha256(url.encode("utf-8")).hexdigest()[:32] + ext
    target = DIST / "images" / name
    if target.is_file():
        return name
    try:
        data = http_get(url, retries=2, timeout=60)
    except Exception as exc:
        print(f"  ! картинка не скачалась ({url}): {exc}", file=sys.stderr)
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return name


def main() -> int:
    started = time.time()
    if DIST.exists():
        shutil.rmtree(DIST)
    (DIST / "artifacts").mkdir(parents=True, exist_ok=True)
    (DIST / "images").mkdir(parents=True, exist_ok=True)

    print(f"Источник: {SOURCE_STORE}")
    plugins: list[dict[str, Any]] = json.loads(http_get(SOURCE_STORE))
    plugins = [p for p in plugins if p.get("visible", True) and p.get("versions")]
    print(f"Плагинов в сторе: {len(plugins)}")

    # Какие версии зеркалим: KEEP_VERSIONS самых свежих у каждого плагина.
    wanted: dict[str, str] = {}  # hash -> "Плагин 1.2.3"
    for plugin in plugins:
        for version in plugin["versions"][:KEEP_VERSIONS]:
            wanted[version["hash"]] = f"{plugin['name']} {version['name']}"

    print(f"Архивов к зеркалированию: {len(wanted)}")
    ok: dict[str, Path] = {}
    failed: dict[str, str] = {}

    def work(item: tuple[str, str]) -> None:
        hash_, label = item
        try:
            ok[hash_] = fetch_artifact(hash_)
        except Exception as exc:
            failed[hash_] = f"{label}: {exc}"
            print(f"  ! {label}: {exc}", file=sys.stderr)

    with concurrent.futures.ThreadPoolExecutor(WORKERS) as pool:
        list(pool.map(work, wanted.items()))

    # Копируем в dist то, что влезает в лимит Pages на размер файла.
    too_big: dict[str, int] = {}
    on_pages: set[str] = set()
    for hash_, path in ok.items():
        size = path.stat().st_size
        if size > MAX_PAGES_FILE_BYTES:
            too_big[hash_] = size
            continue
        shutil.copyfile(path, DIST / "artifacts" / f"{hash_}.zip")
        on_pages.add(hash_)

    # Собираем два варианта JSON: архивы с Pages и архивы из GitHub Releases.
    mirrored_plugins: list[dict[str, Any]] = []
    binary_notes: dict[str, list[str]] = {}
    total_bytes = 0

    for plugin in sorted(plugins, key=lambda p: p["name"].lower()):
        versions = [v for v in plugin["versions"][:KEEP_VERSIONS] if v["hash"] in ok]
        if not versions:
            continue
        entry = dict(plugin)
        entry["versions"] = [dict(v) for v in versions]
        image = mirror_image(plugin.get("image_url", ""))
        entry["_image_file"] = image
        mirrored_plugins.append(entry)
        for version in versions:
            total_bytes += ok[version["hash"]].stat().st_size
        hosts = remote_binary_hosts(ok[versions[0]["hash"]])
        if hosts:
            binary_notes[plugin["name"]] = hosts

    def render(artifact_base: str, use_pages_only: bool) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for entry in mirrored_plugins:
            item = {k: v for k, v in entry.items() if k != "_image_file"}
            versions = []
            for version in entry["versions"]:
                hash_ = version["hash"]
                if use_pages_only and hash_ not in on_pages:
                    continue
                version = dict(version)
                version["artifact"] = f"{artifact_base}/{hash_}.zip"
                versions.append(version)
            if not versions:
                continue
            item["versions"] = versions
            if entry["_image_file"] and PAGES_BASE:
                item["image_url"] = f"{PAGES_BASE}/images/{entry['_image_file']}"
            out.append(item)
        return out

    pages_json = render(f"{PAGES_BASE}/artifacts", use_pages_only=True)
    release_json = render(RELEASE_BASE or f"{PAGES_BASE}/artifacts", use_pages_only=False)

    for name, payload in (
        ("plugins", pages_json),
        ("plugins.json", pages_json),
        ("plugins-gh", release_json),
        ("plugins-gh.json", release_json),
    ):
        (DIST / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    status = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": SOURCE_STORE,
        "plugins_upstream": len(plugins),
        "plugins_mirrored": len(pages_json),
        "artifacts_mirrored": len(on_pages),
        "artifacts_total_bytes": total_bytes,
        "keep_versions": KEEP_VERSIONS,
        "store_url": f"{PAGES_BASE}/plugins" if PAGES_BASE else None,
        "store_url_releases": f"{PAGES_BASE}/plugins-gh" if PAGES_BASE else None,
        "too_big_for_pages": {wanted[h]: s for h, s in too_big.items()},
        "failed": list(failed.values()),
        "plugins_with_remote_binaries": binary_notes,
        "sync_seconds": round(time.time() - started, 1),
    }
    (DIST / "status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (DIST / "index.html").write_text(render_index(status, pages_json), encoding="utf-8")

    print(
        f"Готово: {len(pages_json)} плагинов, {len(on_pages)} архивов, "
        f"{total_bytes / 1e6:.1f} МБ, ошибок: {len(failed)}"
    )
    # Падаем, только если зеркало получилось пустым — единичные сбои не страшны.
    return 1 if not pages_json else 0


def render_index(status: dict[str, Any], plugins: list[dict[str, Any]]) -> str:
    rows = "\n".join(
        '<tr><td>{name}</td><td>{author}</td><td>{version}</td>'
        '<td><a href="{artifact}">zip</a></td></tr>'.format(
            name=html.escape(p["name"]),
            author=html.escape(p.get("author") or ""),
            version=html.escape(p["versions"][0]["name"]),
            artifact=html.escape(p["versions"][0]["artifact"]),
        )
        for p in plugins
    )
    store_url = html.escape(status.get("store_url") or "")
    alt_url = html.escape(status.get("store_url_releases") or "")
    notes = status["plugins_with_remote_binaries"]
    notes_html = ""
    if notes:
        items = "".join(
            f"<li>{html.escape(name)} — {html.escape(', '.join(hosts))}</li>"
            for name, hosts in sorted(notes.items())
        )
        notes_html = (
            "<h2>Докачивают файлы со сторонних адресов</h2>"
            "<p>Эти плагины при установке тянут бинарники мимо зеркала — "
            "если они не ставятся, дело в этих доменах.</p>"
            f"<ul>{items}</ul>"
        )
    failed_html = ""
    if status["failed"]:
        items = "".join(f"<li>{html.escape(x)}</li>" for x in status["failed"])
        failed_html = f"<h2>Не зеркалировалось</h2><ul>{items}</ul>"
    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Зеркало магазина Decky</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font: 16px/1.6 system-ui, sans-serif; max-width: 52rem; margin: 2rem auto; padding: 0 1rem; }}
  code {{ background: rgba(127,127,127,.18); padding: .15em .4em; border-radius: .25em; word-break: break-all; }}
  table {{ border-collapse: collapse; width: 100%; }}
  td, th {{ text-align: left; padding: .3rem .6rem; border-bottom: 1px solid rgba(127,127,127,.3); }}
  .url {{ font-size: 1.1rem; }}
</style></head><body>
<h1>Зеркало магазина плагинов Decky</h1>
<p>Вставь этот адрес в Decky → Settings → General → Store channel → Custom:</p>
<p class="url"><code>{store_url}</code></p>
<p>Запасной вариант (архивы отдаются из GitHub Releases): <code>{alt_url}</code></p>
<h2>Состояние</h2>
<ul>
  <li>Обновлено: {html.escape(status['generated_at'])}</li>
  <li>Плагинов: {status['plugins_mirrored']} из {status['plugins_upstream']}</li>
  <li>Архивов: {status['artifacts_mirrored']} ({status['artifacts_total_bytes'] / 1e6:.1f} МБ)</li>
</ul>
{failed_html}
{notes_html}
<h2>Плагины</h2>
<p>Если магазин почему-то не грузится, плагин можно поставить вручную: скопируй
ссылку на zip и вставь в Decky → Settings → Developer mode → Install Plugin from URL.</p>
<table><thead><tr><th>Название</th><th>Автор</th><th>Версия</th><th>Архив</th></tr></thead>
<tbody>
{rows}
</tbody></table>
</body></html>
"""


if __name__ == "__main__":
    sys.exit(main())
