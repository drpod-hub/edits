#!/usr/bin/env python3
"""Baixa arquivos XML a partir de uma lista de URLs e/ou de páginas com links.

Usa só a biblioteca padrão do Python (não precisa instalar nada).

Exemplos:
    # links num arquivo de texto (um por linha)
    python baixar_xml.py -l links.txt

    # links direto na linha de comando
    python baixar_xml.py https://site.com/a.xml https://site.com/b.xml

    # varre uma página e baixa todos os links que terminam em .xml
    python baixar_xml.py -p https://site.com/arquivos/

    # escolhe a pasta de destino e baixa 8 arquivos ao mesmo tempo
    python baixar_xml.py -l links.txt -o meus_xmls -j 8
"""

import argparse
import concurrent.futures
import hashlib
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

USER_AGENT = "Mozilla/5.0 (baixar_xml; +https://www.python.org)"
CAPTCHA_HINTS = (b"captcha", b"recaptcha", b"hcaptcha", b"cf-challenge")


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            for name, value in attrs:
                if name == "href" and value:
                    self.links.append(value)


def fetch(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(), resp.headers


def links_from_page(page_url, pattern, timeout):
    body, headers = fetch(page_url, timeout)
    charset = headers.get_content_charset() or "utf-8"
    parser = LinkParser()
    parser.feed(body.decode(charset, errors="replace"))
    regex = re.compile(pattern, re.IGNORECASE)
    found = []
    for href in parser.links:
        url = urllib.parse.urljoin(page_url, href)
        if regex.search(urllib.parse.urlparse(url).path) and url not in found:
            found.append(url)
    return found


def links_from_file(path):
    with open(path, encoding="utf-8-sig") as f:
        return [
            line.strip()
            for line in f
            if line.strip() and not line.lstrip().startswith("#")
        ]


def filename_for(url, headers=None):
    if headers:
        cd = headers.get("Content-Disposition", "")
        m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', cd, re.IGNORECASE)
        if m:
            return safe_name(urllib.parse.unquote(m.group(1)))
    name = os.path.basename(urllib.parse.urlparse(url).path)
    name = safe_name(urllib.parse.unquote(name))
    if not name:
        name = hashlib.sha1(url.encode()).hexdigest()[:12]
    if not name.lower().endswith(".xml"):
        name += ".xml"
    return name


def safe_name(name):
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(". ")


def unique_path(folder, name):
    path = os.path.join(folder, name)
    base, ext = os.path.splitext(path)
    n = 2
    while os.path.exists(path):
        path = f"{base}_{n}{ext}"
        n += 1
    return path


def download(url, folder, timeout, retries, overwrite, validate):
    expected = os.path.join(folder, filename_for(url))
    if not overwrite and os.path.exists(expected):
        return "pulado", url, expected

    body = headers = last_error = None
    for attempt in range(1, max(1, retries) + 1):
        try:
            body, headers = fetch(url, timeout)
            break
        except urllib.error.HTTPError as e:
            last_error = f"HTTP {e.code}"
            if e.code in (401, 403, 404, 410):
                break
        except Exception as e:  # rede, timeout, etc.
            last_error = str(e)
        if attempt < retries:
            time.sleep(2 ** attempt)
    if body is None:
        return "erro", url, last_error

    head = body[:4096].lower()
    if b"<html" in head and any(h in head for h in CAPTCHA_HINTS):
        return "erro", url, "o site pediu captcha (não é possível baixar automaticamente)"

    if validate:
        try:
            ET.fromstring(body)
        except ET.ParseError as e:
            return "erro", url, f"conteúdo não é um XML válido ({e})"

    name = filename_for(url, headers)
    path = os.path.join(folder, name) if overwrite else unique_path(folder, name)
    with open(path, "wb") as f:
        f.write(body)
    return "ok", url, path


def main():
    ap = argparse.ArgumentParser(
        description="Baixa arquivos XML de uma lista de URLs ou de páginas com links."
    )
    ap.add_argument("urls", nargs="*", help="URLs de arquivos XML")
    ap.add_argument("-l", "--lista", action="append", default=[],
                    help="arquivo .txt com uma URL por linha (pode repetir)")
    ap.add_argument("-p", "--pagina", action="append", default=[],
                    help="página para procurar links de XML (pode repetir)")
    ap.add_argument("--filtro", default=r"\.xml$",
                    help=r"regex aplicada aos links da página (padrão: \.xml$)")
    ap.add_argument("-o", "--saida", default="xmls", help="pasta de destino (padrão: xmls)")
    ap.add_argument("-j", "--paralelo", type=int, default=4,
                    help="downloads simultâneos (padrão: 4)")
    ap.add_argument("--timeout", type=int, default=30, help="timeout em segundos (padrão: 30)")
    ap.add_argument("--tentativas", type=int, default=3, help="tentativas por arquivo (padrão: 3)")
    ap.add_argument("--sobrescrever", action="store_true",
                    help="baixa de novo mesmo se o arquivo já existir")
    ap.add_argument("--sem-validar", action="store_true",
                    help="não verifica se o conteúdo é XML válido")
    args = ap.parse_args()

    urls = list(args.urls)
    for path in args.lista:
        urls += links_from_file(path)
    for page in args.pagina:
        try:
            found = links_from_page(page, args.filtro, args.timeout)
            print(f"{len(found)} link(s) encontrado(s) em {page}")
            urls += found
        except Exception as e:
            print(f"[erro] não consegui ler a página {page}: {e}", file=sys.stderr)

    urls = list(dict.fromkeys(urls))  # remove duplicados mantendo a ordem
    if not urls:
        ap.error("nenhuma URL informada (use URLs, -l lista.txt ou -p pagina)")

    os.makedirs(args.saida, exist_ok=True)
    print(f"Baixando {len(urls)} arquivo(s) para '{args.saida}'...")

    counts = {"ok": 0, "pulado": 0, "erro": 0}
    errors = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.paralelo)) as pool:
        futures = [
            pool.submit(download, u, args.saida, args.timeout, args.tentativas,
                        args.sobrescrever, not args.sem_validar)
            for u in urls
        ]
        for i, fut in enumerate(concurrent.futures.as_completed(futures), 1):
            status, url, info = fut.result()
            counts[status] += 1
            print(f"[{i}/{len(urls)}] {status:6} {url}" + (f" -> {info}" if status == "erro" else ""))
            if status == "erro":
                errors.append(f"{url}\t{info}")

    if errors:
        log = os.path.join(args.saida, "erros.txt")
        with open(log, "w", encoding="utf-8") as f:
            f.write("\n".join(errors) + "\n")
        print(f"Lista de erros salva em {log}")

    print(f"\nConcluído: {counts['ok']} baixado(s), {counts['pulado']} já existia(m), "
          f"{counts['erro']} erro(s).")
    return 1 if counts["erro"] else 0


if __name__ == "__main__":
    sys.exit(main())
