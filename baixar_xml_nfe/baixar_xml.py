#!/usr/bin/env python3
"""Baixa XMLs de NF-e a partir das chaves de acesso.

Usa o web service oficial NFeDistribuicaoDFe (Ambiente Nacional da SEFAZ),
consulta por chave (consChNFe). É preciso o certificado digital A1 (.pfx) de
uma empresa que seja parte da nota: emitente, destinatário ou transportador.

Exemplos:
    python3 baixar_xml.py --pfx empresa.pfx --senha 1234 --uf SP chaves.txt
    python3 baixar_xml.py --pfx empresa.pfx --uf SP 3524...0001 3524...0002
"""

import argparse
import base64
import getpass
import gzip
import os
import re
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

import requests
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    pkcs12,
)

URLS = {
    1: "https://www1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx",
    2: "https://hom1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx",
}
SOAP_ACTION = "http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe/nfeDistDFeInteresse"
NS = {"nfe": "http://www.portalfiscal.inf.br/nfe"}

UF_CODIGOS = {
    "RO": 11, "AC": 12, "AM": 13, "RR": 14, "PA": 15, "AP": 16, "TO": 17,
    "MA": 21, "PI": 22, "CE": 23, "RN": 24, "PB": 25, "PE": 26, "AL": 27,
    "SE": 28, "BA": 29, "MG": 31, "ES": 32, "RJ": 33, "SP": 35, "PR": 41,
    "SC": 42, "RS": 43, "MS": 50, "MT": 51, "GO": 52, "DF": 53,
}


def chave_valida(chave):
    """Confere tamanho e dígito verificador (módulo 11) da chave de acesso."""
    if not re.fullmatch(r"\d{44}", chave):
        return False
    soma = sum(int(d) * p for d, p in zip(reversed(chave[:43]), [2, 3, 4, 5, 6, 7, 8, 9] * 6))
    dv = 11 - soma % 11
    return (0 if dv >= 10 else dv) == int(chave[43])


def ler_chaves(entradas):
    """Aceita chaves soltas ou arquivos (txt/csv/qualquer texto) contendo chaves."""
    chaves = []
    for entrada in entradas:
        if os.path.isfile(entrada):
            with open(entrada, encoding="utf-8", errors="ignore") as f:
                texto = f.read()
        else:
            texto = entrada
        # Remove espaços/pontos que às vezes separam os blocos da chave
        texto = re.sub(r"(?<=\d)[ .\-](?=\d)", "", texto)
        chaves += re.findall(r"(?<!\d)\d{44}(?!\d)", texto)
    return list(dict.fromkeys(chaves))  # sem duplicadas, mantendo a ordem


def carregar_certificado(caminho_pfx, senha):
    """Converte o .pfx em arquivos PEM temporários (o requests só aceita PEM)."""
    with open(caminho_pfx, "rb") as f:
        chave, cert, extras = pkcs12.load_key_and_certificates(f.read(), senha.encode())
    pasta = tempfile.mkdtemp(prefix="cert_nfe_")
    cert_pem = os.path.join(pasta, "cert.pem")
    key_pem = os.path.join(pasta, "key.pem")
    with open(cert_pem, "wb") as f:
        f.write(cert.public_bytes(Encoding.PEM))
        for extra in extras or []:
            f.write(extra.public_bytes(Encoding.PEM))
    fd = os.open(key_pem, os.O_WRONLY | os.O_CREAT, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(chave.private_bytes(Encoding.PEM, PrivateFormat.TraditionalOpenSSL, NoEncryption()))
    # Certificados e-CNPJ costumam trazer "RAZAO SOCIAL:CNPJ" no CN
    cn = cert.subject.rfc4514_string()
    achado = re.search(r"(\d{14})", cn)
    return (cert_pem, key_pem), pasta, achado.group(1) if achado else None


def montar_envelope(chave, cnpj, cuf, tp_amb):
    doc = "CPF" if len(cnpj) == 11 else "CNPJ"
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">'
        "<soap12:Body>"
        '<nfeDistDFeInteresse xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe">'
        "<nfeDadosMsg>"
        '<distDFeInt xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.01">'
        f"<tpAmb>{tp_amb}</tpAmb><cUFAutor>{cuf}</cUFAutor><{doc}>{cnpj}</{doc}>"
        f"<consChNFe><chNFe>{chave}</chNFe></consChNFe>"
        "</distDFeInt></nfeDadosMsg></nfeDistDFeInteresse>"
        "</soap12:Body></soap12:Envelope>"
    )


def interpretar_resposta(xml_resposta):
    """Devolve (cStat, xMotivo, [(schema, xml_str), ...])."""
    raiz = ET.fromstring(xml_resposta)
    ret = raiz.find(".//nfe:retDistDFeInt", NS)
    if ret is None:
        raise ValueError("Resposta sem retDistDFeInt: " + xml_resposta[:500])
    cstat = ret.findtext("nfe:cStat", namespaces=NS)
    motivo = ret.findtext("nfe:xMotivo", namespaces=NS)
    docs = []
    for doc in ret.findall(".//nfe:docZip", NS):
        conteudo = gzip.decompress(base64.b64decode(doc.text)).decode("utf-8")
        docs.append((doc.get("schema", ""), conteudo))
    return cstat, motivo, docs


def baixar(sessao, url, chave, cnpj, cuf, tp_amb):
    resposta = sessao.post(
        url,
        data=montar_envelope(chave, cnpj, cuf, tp_amb).encode("utf-8"),
        headers={"Content-Type": f'application/soap+xml; charset=utf-8; action="{SOAP_ACTION}"'},
        timeout=60,
    )
    resposta.raise_for_status()
    return interpretar_resposta(resposta.text)


def main():
    p = argparse.ArgumentParser(description="Baixa XMLs de NF-e pelas chaves de acesso (SEFAZ / NFeDistribuicaoDFe).")
    p.add_argument("entradas", nargs="+", help="chaves de acesso e/ou arquivos com chaves (uma por linha, CSV etc.)")
    p.add_argument("--pfx", required=True, help="certificado digital A1 (.pfx/.p12)")
    p.add_argument("--senha", help="senha do certificado (se omitida, é pedida no terminal)")
    p.add_argument("--uf", required=True, help="UF da empresa do certificado (ex.: SP)")
    p.add_argument("--cnpj", help="CNPJ/CPF interessado (padrão: lido do certificado)")
    p.add_argument("--saida", default="xmls", help="pasta de destino (padrão: xmls)")
    p.add_argument("--homologacao", action="store_true", help="usa o ambiente de homologação")
    p.add_argument("--intervalo", type=float, default=2.0, help="segundos entre consultas (padrão: 2)")
    args = p.parse_args()

    uf = args.uf.upper()
    if uf not in UF_CODIGOS:
        p.error(f"UF inválida: {args.uf}")

    chaves = ler_chaves(args.entradas)
    if not chaves:
        p.error("nenhuma chave de 44 dígitos encontrada")

    senha = args.senha if args.senha is not None else getpass.getpass("Senha do certificado: ")
    cert, pasta_cert, cnpj_cert = carregar_certificado(args.pfx, senha)
    cnpj = re.sub(r"\D", "", args.cnpj or cnpj_cert or "")
    if len(cnpj) not in (11, 14):
        p.error("não consegui ler o CNPJ do certificado; informe com --cnpj")

    tp_amb = 2 if args.homologacao else 1
    os.makedirs(args.saida, exist_ok=True)
    sessao = requests.Session()
    sessao.cert = cert

    completos, resumos, falhas = 0, [], []
    try:
        for i, chave in enumerate(chaves, 1):
            prefixo = f"[{i}/{len(chaves)}] {chave}"
            if not chave_valida(chave):
                print(f"{prefixo}: chave inválida (dígito verificador)")
                falhas.append(chave)
                continue
            if chave[20:22] != "55":
                print(f"{prefixo}: aviso - modelo {chave[20:22]} (só NF-e modelo 55 está no Ambiente Nacional)")
            try:
                cstat, motivo, docs = baixar(sessao, URLS[tp_amb], chave, cnpj, UF_CODIGOS[uf], tp_amb)
            except (requests.RequestException, ValueError, OSError) as e:
                print(f"{prefixo}: erro - {e}")
                falhas.append(chave)
                continue

            if cstat != "138" or not docs:
                print(f"{prefixo}: {cstat} - {motivo}")
                falhas.append(chave)
            for schema, conteudo in docs:
                if schema.startswith("procNFe"):
                    nome, completos = f"{chave}-procNFe.xml", completos + 1
                elif schema.startswith("resNFe"):
                    nome = f"{chave}-resumo.xml"
                    resumos.append(chave)
                else:  # eventos (cancelamento, CC-e...) vindos junto
                    nome = f"{chave}-{schema.split('_')[0]}.xml"
                with open(os.path.join(args.saida, nome), "w", encoding="utf-8") as f:
                    f.write(conteudo)
                print(f"{prefixo}: salvo {nome}")

            if cstat == "656":  # consumo indevido: SEFAZ bloqueou temporariamente
                print("SEFAZ bloqueou por consumo indevido; aguarde ~1 hora e rode de novo com as chaves restantes.")
                falhas += chaves[i:]
                break
            if i < len(chaves):
                time.sleep(args.intervalo)
    finally:
        for nome in os.listdir(pasta_cert):
            os.remove(os.path.join(pasta_cert, nome))
        os.rmdir(pasta_cert)

    print(f"\nXMLs completos: {completos} | só resumo: {len(resumos)} | falhas: {len(falhas)}")
    if resumos:
        print("Para notas que vieram só como resumo, faça a manifestação 'Ciência da Operação' "
              "e rode novamente para receber o XML completo.")
    if falhas:
        caminho = os.path.join(args.saida, "falhas.txt")
        with open(caminho, "w") as f:
            f.write("\n".join(falhas) + "\n")
        print(f"Chaves com falha salvas em {caminho}")
    return 0 if not falhas else 1


if __name__ == "__main__":
    sys.exit(main())
