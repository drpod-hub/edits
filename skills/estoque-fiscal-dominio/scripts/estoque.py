#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Estoque fiscal: le notas e planilhas, apura o inventario e gera as saidas.

Comandos:
  ler-xml       XMLs de NF-e/NFC-e (pastas, arquivos ou .zip) -> movimentos.csv
  ler-planilha  planilha do cliente ou relatorio do Dominio   -> inventario padrao (CSV)
  apurar        movimentos/contagem -> inventario.csv + pendencias + ficha
  conferir      valida um inventario.csv
  gerar         inventario.csv -> Excel, Livro Registro de Inventario (PDF), arquivo do Dominio

Todos os CSV usam ';' como separador, UTF-8 com BOM e virgula decimal (abrem direto no Excel).
"""
import argparse
import csv
import datetime as dt
import difflib
import io
import json
import os
import re
import sys
import unicodedata
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP, ROUND_DOWN, InvalidOperation

Z = Decimal("0")
C2 = Decimal("0.01")
C3 = Decimal("0.001")
C6 = Decimal("0.000001")

COLS_MOV = ["data", "tipo", "natureza", "movimenta", "modelo", "numero", "serie", "chave",
            "cfop", "participante", "cnpj_participante", "codigo_origem", "codigo", "fator",
            "ean", "descricao", "ncm", "unidade", "quantidade", "unidade_trib",
            "quantidade_trib", "valor_produtos", "desconto", "frete", "seguro", "outras",
            "ii", "ipi", "icms_cst", "icms", "icms_cred_sn", "icms_st", "pis_cst",
            "custo_informado", "observacao"]
COLS_INV = ["codigo", "descricao", "ncm", "unidade", "quantidade", "custo_unitario",
            "valor_total", "grupo", "ean", "observacao"]
COLS_NUM = {"quantidade", "quantidade_trib", "valor_produtos", "desconto", "frete", "seguro",
            "outras", "ii", "ipi", "icms", "icms_cred_sn", "icms_st", "custo_informado",
            "custo_unitario", "valor_total", "fator"}

# ---- CFOP: o que mexe no estoque proprio (pelos 3 ultimos digitos) -------------------
ENT_COMPRA = {"101", "102", "111", "113", "116", "117", "118", "120", "121", "122", "127",
              "401", "403", "651", "652", "653"}
ENT_DEVOL = {"201", "202", "203", "204", "410", "411", "660", "661", "662"}
TRANSF = {"151", "152", "408", "409", "658", "659"}
SAI_VENDA = {"101", "102", "103", "104", "105", "106", "107", "108", "109", "110", "111",
             "112", "113", "114", "115", "116", "117", "118", "119", "120", "122", "123",
             "401", "402", "403", "404", "405", "501", "502", "651", "652", "653", "654",
             "655", "656", "667"}
SAI_DEVOL = {"201", "202", "208", "209", "410", "411"}
SAI_OUTRAS = {"910", "911", "927"}
REVISAR = {"949", "923", "924"}


def classificar_cfop(tipo, cfop, emissao_propria):
    """Devolve (natureza, movimenta S/N/R, observacao)."""
    cfop = re.sub(r"\D", "", cfop or "")
    if len(cfop) != 4:
        return "indefinida", "R", "CFOP ausente ou invalido"
    suf, pri = cfop[1:], cfop[0]
    if suf in REVISAR:
        return "revisar", "R", "CFOP generico (%s): confirmar se mexe no estoque" % cfop
    if tipo == "E":
        if pri in "567":  # nota do fornecedor: o CFOP e o de saida dele
            if suf in SAI_VENDA:
                return "compra", "S", ""
            if suf in SAI_DEVOL:
                return "devolucao_venda", "S", "cliente devolveu mercadoria"
            if suf in TRANSF:
                return "transf_entrada", "S", ""
            if suf in {"910", "911"}:
                return "bonificacao", "S", "bonificacao/brinde/amostra recebida"
            return "outras", "N", "CFOP %s do emitente nao e compra para estoque" % cfop
        if suf in ENT_COMPRA:
            return "compra", "S", ""
        if suf in ENT_DEVOL:
            return "devolucao_venda", "S", ""
        if suf in TRANSF:
            return "transf_entrada", "S", ""
        if suf == "910":
            return "bonificacao", "S", ""
        return "outras", "N", "CFOP %s nao movimenta estoque proprio" % cfop
    if suf in SAI_VENDA:
        return "venda", "S", ""
    if suf in SAI_DEVOL:
        return "devolucao_compra", "S", ""
    if suf in TRANSF:
        return "transf_saida", "S", ""
    if suf in SAI_OUTRAS:
        return "outras_saidas", "S", "bonificacao/brinde/perda"
    if suf == "929":
        return "outras", "N", "5929: venda ja registrada em cupom/NFC-e (evita duplicar)"
    return "outras", "N", "CFOP %s nao movimenta estoque proprio" % cfop


# ---- utilitarios ----------------------------------------------------------------------
def dec(v):
    if v is None:
        return Z
    if isinstance(v, Decimal):
        return v
    if isinstance(v, (int, float)):
        return Decimal(str(v))
    s = str(v).strip().replace("R$", "").replace(" ", "").replace("\xa0", "")
    if not s:
        return Z
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        d = Decimal(s)
    except InvalidOperation:
        return Z
    return -d if neg else d


def fmt(d, casas=None):
    if d is None:
        return ""
    d = Decimal(d)
    if casas is not None:
        d = d.quantize(Decimal(1).scaleb(-casas), rounding=ROUND_HALF_UP)
    s = format(d, "f")
    if "." in s and casas is None:
        s = s.rstrip("0").rstrip(".")
    return s.replace(".", ",")


def brl(d):
    s = "{:,.2f}".format(Decimal(d).quantize(C2, rounding=ROUND_HALF_UP))
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^A-Za-z0-9 ]", " ", s)).strip().upper()


def so_digitos(s):
    return re.sub(r"\D", "", str(s or ""))


def ean_valido(e):
    e = so_digitos(e)
    return e if len(e) in (8, 12, 13, 14) and int(e) > 0 else ""


def data_br(s):
    s = str(s or "").strip()
    for f in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%Y", "%Y%m%d"):
        try:
            return dt.datetime.strptime(s[:10] if f != "%Y%m%d" else s[:8], f).date()
        except ValueError:
            pass
    return None


def ler_csv(caminho):
    with open(caminho, "r", encoding="utf-8-sig", newline="") as f:
        amostra = f.read(4096)
        f.seek(0)
        sep = ";" if amostra.count(";") >= amostra.count(",") else ","
        linhas = []
        for r in csv.DictReader(f, delimiter=sep):
            linhas.append({(k or "").strip().lower(): (v or "").strip() for k, v in r.items()})
        return linhas


def gravar_csv(caminho, colunas, linhas):
    os.makedirs(os.path.dirname(os.path.abspath(caminho)), exist_ok=True)
    with open(caminho, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(colunas)
        for l in linhas:
            out = []
            for c in colunas:
                v = l.get(c, "")
                if isinstance(v, Decimal):
                    v = fmt(v)
                elif isinstance(v, dt.date):
                    v = v.strftime("%d/%m/%Y")
                out.append(v)
            w.writerow(out)


def ler_inventario(caminho):
    itens = []
    for r in ler_csv(caminho):
        if not (r.get("codigo") or r.get("descricao")):
            continue
        q, cu, vt = dec(r.get("quantidade")), dec(r.get("custo_unitario")), dec(r.get("valor_total"))
        if not cu and q:
            cu = (vt / q).quantize(C6, rounding=ROUND_HALF_UP)
        if not vt:
            vt = (q * cu).quantize(C2, rounding=ROUND_HALF_UP)
        itens.append({"codigo": r.get("codigo", ""), "descricao": r.get("descricao", ""),
                      "ncm": so_digitos(r.get("ncm")), "unidade": (r.get("unidade") or "UN").upper(),
                      "quantidade": q, "custo_unitario": cu, "valor_total": vt,
                      "grupo": r.get("grupo") or "00", "ean": ean_valido(r.get("ean")),
                      "observacao": r.get("observacao", "")})
    return itens


# ---- ler-xml --------------------------------------------------------------------------
def _sem_ns(raiz):
    for el in raiz.iter():
        if isinstance(el.tag, str) and "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    return raiz


def _t(el, caminho, padrao=""):
    if el is None:
        return padrao
    x = el.find(caminho)
    return (x.text or "").strip() if x is not None and x.text else padrao


def _iter_xml(origens):
    for o in origens:
        if os.path.isdir(o):
            for raiz, _, arqs in os.walk(o):
                for a in sorted(arqs):
                    yield from _iter_xml([os.path.join(raiz, a)])
        elif o.lower().endswith(".zip"):
            with zipfile.ZipFile(o) as z:
                for n in sorted(z.namelist()):
                    if n.lower().endswith(".xml"):
                        yield o + "!" + n, z.read(n)
        elif o.lower().endswith(".xml"):
            with open(o, "rb") as f:
                yield o, f.read()


def cmd_ler_xml(a):
    cnpj = so_digitos(a.cnpj)
    if len(cnpj) not in (11, 14):
        sys.exit("ERRO: informe --cnpj da empresa (14 digitos).")
    notas, canceladas, cont = {}, set(), defaultdict(int)
    for nome, bruto in _iter_xml(a.origens):
        cont["arquivos"] += 1
        try:
            raiz = _sem_ns(ET.fromstring(bruto))
        except ET.ParseError:
            cont["xml_invalido"] += 1
            continue
        for ev in raiz.iter("infEvento"):
            if _t(ev, "tpEvento") == "110111" and _t(ev, "chNFe"):
                canceladas.add(_t(ev, "chNFe"))
        inf = next(raiz.iter("infNFe"), None)
        if inf is None:
            if next(raiz.iter("infEvento"), None) is None:
                cont["nao_e_nfe"] += 1
            continue
        chave = so_digitos(inf.get("Id", ""))[-44:]
        prot = next(raiz.iter("infProt"), None)
        cstat = _t(prot, "cStat")
        if cstat in {"101", "135", "151", "155"}:
            canceladas.add(chave)
        if cstat in {"110", "301", "302", "303"}:
            cont["denegadas"] += 1
            continue
        if chave in notas:
            cont["duplicadas"] += 1
            continue
        notas[chave] = (nome, inf, cstat)

    linhas = []
    for chave, (nome, inf, cstat) in notas.items():
        if chave in canceladas:
            cont["canceladas"] += 1
            continue
        ide, emit, dest = inf.find("ide"), inf.find("emit"), inf.find("dest")
        c_emit = _t(emit, "CNPJ") or _t(emit, "CPF")
        c_dest = _t(dest, "CNPJ") or _t(dest, "CPF")
        tpnf, fin = _t(ide, "tpNF"), _t(ide, "finNFe")
        obs_nota = []
        if c_emit == cnpj:
            tipo, propria = ("S" if tpnf == "1" else "E"), True
            part, c_part = _t(dest, "xNome"), c_dest
        elif c_dest == cnpj:
            tipo, propria = "E", False
            part, c_part = _t(emit, "xNome"), c_emit
            if tpnf == "0":
                obs_nota.append("nota de ENTRADA do emitente contra a empresa: conferir")
        else:
            cont["de_terceiros"] += 1
            continue
        if not cstat:
            obs_nota.append("XML sem protocolo de autorizacao")
        if fin == "3":
            cont["ajuste_ignoradas"] += 1
            continue
        if fin == "2":
            obs_nota.append("nota complementar")
        data = data_br(_t(ide, "dhEmi") or _t(ide, "dEmi"))
        if a.de and data and data < a.de or a.ate and data and data > a.ate:
            cont["fora_do_periodo"] += 1
            continue
        cont["notas_%s" % ("saida" if tipo == "S" else "entrada")] += 1
        for det in inf.findall("det"):
            p, imp = det.find("prod"), det.find("imposto")
            icms = next(iter(imp.find("ICMS")), None) if imp is not None and imp.find("ICMS") is not None else None
            pis = next(iter(imp.find("PIS")), None) if imp is not None and imp.find("PIS") is not None else None
            ipi = imp.find("IPI/IPITrib") if imp is not None else None
            cfop = _t(p, "CFOP")
            nat, mov, obs = classificar_cfop(tipo, cfop, propria)
            if tpnf == "0" and not propria:
                mov = "R"
            observ = "; ".join([x for x in obs_nota + [obs] if x])
            st = dec(_t(icms, "vICMSST")) + dec(_t(icms, "vFCPST"))
            linhas.append({
                "data": data, "tipo": tipo, "natureza": nat, "movimenta": mov,
                "modelo": _t(ide, "mod"), "numero": _t(ide, "nNF"), "serie": _t(ide, "serie"),
                "chave": chave, "cfop": cfop, "participante": part, "cnpj_participante": c_part,
                "codigo_origem": _t(p, "cProd"), "codigo": _t(p, "cProd") if propria else "",
                "fator": "", "ean": ean_valido(_t(p, "cEAN")) or ean_valido(_t(p, "cEANTrib")),
                "descricao": _t(p, "xProd"), "ncm": _t(p, "NCM"),
                "unidade": _t(p, "uCom").upper(), "quantidade": dec(_t(p, "qCom")),
                "unidade_trib": _t(p, "uTrib").upper(), "quantidade_trib": dec(_t(p, "qTrib")),
                "valor_produtos": dec(_t(p, "vProd")), "desconto": dec(_t(p, "vDesc")),
                "frete": dec(_t(p, "vFrete")), "seguro": dec(_t(p, "vSeg")),
                "outras": dec(_t(p, "vOutro")), "ii": dec(_t(imp, "II/vII")),
                "ipi": dec(_t(ipi, "vIPI")),
                "icms_cst": _t(icms, "CST") or _t(icms, "CSOSN"),
                "icms": dec(_t(icms, "vICMS")), "icms_cred_sn": dec(_t(icms, "vCredICMSSN")),
                "icms_st": st, "pis_cst": _t(pis, "CST"), "custo_informado": "",
                "observacao": observ})
    linhas.sort(key=lambda l: (l["data"] or dt.date.min, l["tipo"], l["numero"]))
    saida = os.path.join(a.saida, "movimentos.csv")
    gravar_csv(saida, COLS_MOV, linhas)

    print("LEITURA DOS XML")
    for k in ("arquivos", "notas_entrada", "notas_saida", "canceladas", "denegadas", "duplicadas",
              "de_terceiros", "fora_do_periodo", "ajuste_ignoradas", "xml_invalido", "nao_e_nfe"):
        if cont.get(k):
            print("  %-18s %d" % (k, cont[k]))
    datas = [l["data"] for l in linhas if l["data"]]
    if datas:
        print("  periodo            %s a %s" % (min(datas).strftime("%d/%m/%Y"), max(datas).strftime("%d/%m/%Y")))
    tot = defaultdict(lambda: [0, Z])
    for l in linhas:
        k = (l["tipo"], l["natureza"], l["movimenta"])
        tot[k][0] += 1
        tot[k][1] += l["valor_produtos"]
    print("\n  tipo natureza            mov  itens     valor produtos")
    for k in sorted(tot):
        print("  %-4s %-19s %-3s %6d %18s" % (k[0], k[1], k[2], tot[k][0], brl(tot[k][1])))
    forn = defaultdict(lambda: [0, Z, set()])
    for l in linhas:
        if l["tipo"] == "E" and l["movimenta"] == "S" and l["natureza"] == "compra":
            f = forn[(l["cnpj_participante"], l["participante"])]
            f[0] += 1
            f[1] += l["valor_produtos"]
            f[2].add(l["ncm"][:4])
    if forn:
        print("\n  FORNECEDORES tratados como compra para estoque (confirme se algum e uso/consumo ou imobilizado):")
        for (c, n), f in sorted(forn.items(), key=lambda x: -x[1][1]):
            print("  %-14s %-40s %5d itens %15s  NCM %s" % (c, n[:40], f[0], brl(f[1]), ",".join(sorted(f[2]))[:40]))
    rev = [l for l in linhas if l["movimenta"] == "R"]
    if rev:
        print("\n  %d item(ns) com movimenta=R (REVISAR): decida S ou N na coluna 'movimenta'." % len(rev))
    if not cont.get("notas_saida"):
        print("\n  ATENCAO: nenhuma nota de saida. Sem as vendas, o metodo 'movimentacao' nao fecha;"
              " use 'alvo' ou 'contagem', ou peca os XML de venda (NF-e e NFC-e).")
    print("\n  gravado: %s (%d itens)" % (saida, len(linhas)))


# ---- ler-planilha ---------------------------------------------------------------------
SINONIMOS = {
    "codigo": ["codigo do produto", "cod produto", "codigo produto", "cod item", "codigo item",
               "codigo", "cod", "referencia", "ref", "sku", "produto"],
    "ean": ["codigo de barras", "cod barras", "barras", "ean", "gtin"],
    "descricao": ["descricao do produto", "descricao", "discriminacao", "nome do produto", "nome",
                  "produto", "mercadoria", "item"],
    "ncm": ["ncm", "classificacao fiscal", "class fiscal", "cod ncm"],
    "unidade": ["unidade de medida", "unidade", "unid", "und", "un", "um"],
    "quantidade": ["quantidade final", "qtd final", "saldo final", "quantidade", "qtde", "qtd",
                   "quant", "saldo", "estoque", "contagem"],
    "custo_unitario": ["valor unitario", "vl unitario", "vlr unitario", "custo unitario",
                       "custo medio", "preco de custo", "preco custo", "custo", "unitario", "vl unit"],
    "valor_total": ["valor total", "vl total", "vlr total", "valor do item", "total", "valor"],
    "grupo": ["tipo do item", "tipo item", "grupo"],
}


def mapear_cabecalho(celulas):
    """Liga cada campo padrao a um indice de coluna, pelo nome do cabecalho."""
    nomes = [norm(c) for c in celulas]
    mapa, usados = {}, set()
    for campo in ["ean", "ncm", "unidade", "custo_unitario", "valor_total", "quantidade",
                  "grupo", "codigo", "descricao"]:
        achou = None
        for sin in SINONIMOS[campo]:
            s = norm(sin)
            for i, n in enumerate(nomes):
                if i in usados or not n:
                    continue
                if n == s or (len(s) > 3 and re.search(r"\b%s\b" % re.escape(s), n)):
                    achou = i
                    break
            if achou is not None:
                break
        if achou is not None:
            mapa[campo] = achou
            usados.add(achou)
    return mapa


def ler_tabela(caminho, aba=None):
    ext = caminho.lower().rsplit(".", 1)[-1]
    if ext in ("xlsx", "xlsm"):
        import openpyxl
        wb = openpyxl.load_workbook(caminho, data_only=True, read_only=True)
        ws = wb[aba] if aba else wb.worksheets[0]
        return [list(r) for r in ws.iter_rows(values_only=True)]
    if ext == "xls":
        try:
            import xlrd
        except ImportError:
            sys.exit("ERRO: arquivo .xls antigo. Abra no Excel e salve como .xlsx (ou instale xlrd).")
        sh = xlrd.open_workbook(caminho).sheet_by_name(aba) if aba else xlrd.open_workbook(caminho).sheet_by_index(0)
        return [sh.row_values(i) for i in range(sh.nrows)]
    for enc in ("utf-8-sig", "cp1252"):
        try:
            with open(caminho, "r", encoding=enc, newline="") as f:
                txt = f.read()
            break
        except UnicodeDecodeError:
            continue
    sep = max(";\t,|", key=lambda s: txt[:5000].count(s))
    return [r for r in csv.reader(io.StringIO(txt), delimiter=sep)]


def _col_idx(ref, cab):
    ref = ref.strip()
    if re.fullmatch(r"[A-Za-z]{1,2}", ref):
        n = 0
        for ch in ref.upper():
            n = n * 26 + ord(ch) - 64
        return n - 1
    alvo = norm(ref)
    for i, c in enumerate(cab):
        if norm(c) == alvo:
            return i
    sys.exit("ERRO: coluna '%s' nao encontrada no cabecalho." % ref)


def cmd_ler_planilha(a):
    linhas = ler_tabela(a.arquivo, a.aba)
    if a.linha_cabecalho:
        ih = a.linha_cabecalho - 1
    else:
        ih, melhor = 0, -1
        for i, r in enumerate(linhas[:40]):
            n = len(mapear_cabecalho(["" if c is None else c for c in r]))
            if n > melhor:
                ih, melhor = i, n
    cab = ["" if c is None else str(c) for c in linhas[ih]]
    mapa = mapear_cabecalho(cab)
    for par in a.mapa or []:
        campo, ref = par.split("=", 1)
        mapa[campo.strip()] = _col_idx(ref, cab)
    if "quantidade" not in mapa or not ({"codigo", "descricao"} & set(mapa)):
        print("Cabecalho encontrado (linha %d): %s" % (ih + 1, cab))
        sys.exit("ERRO: nao identifiquei as colunas. Use --linha-cabecalho N e/ou "
                 "--mapa codigo=A --mapa descricao=B --mapa quantidade=D ...")

    def val(r, campo):
        i = mapa.get(campo)
        return r[i] if i is not None and i < len(r) and r[i] is not None else ""

    itens, ignoradas = [], 0
    for r in linhas[ih + 1:]:
        cod, desc = str(val(r, "codigo")).strip(), str(val(r, "descricao")).strip()
        if re.fullmatch(r"\d+\.0", cod):
            cod = cod[:-2]
        q = dec(val(r, "quantidade"))
        if not (cod or desc) or norm(cod + desc).startswith("TOTAL") or (not q and not a.manter_zerados):
            ignoradas += 1 if (cod or desc) else 0
            continue
        cu, vt = dec(val(r, "custo_unitario")), dec(val(r, "valor_total"))
        if not cu and vt and q:
            cu = (vt / q).quantize(C6, rounding=ROUND_HALF_UP)
        itens.append({"codigo": cod, "descricao": desc, "ncm": so_digitos(val(r, "ncm")),
                      "unidade": (str(val(r, "unidade")).strip() or "UN").upper(), "quantidade": q,
                      "custo_unitario": cu, "valor_total": vt or (q * cu).quantize(C2),
                      "grupo": so_digitos(val(r, "grupo"))[:2] or "00",
                      "ean": ean_valido(val(r, "ean")), "observacao": ""})
    gravar_csv(a.saida, COLS_INV, itens)
    print("LEITURA DA PLANILHA (cabecalho na linha %d)" % (ih + 1))
    for campo in COLS_INV[:-1]:
        print("  %-15s <- %s" % (campo, cab[mapa[campo]] if campo in mapa else "(nao encontrado)"))
    print("  itens: %d | ignoradas (zeradas/total): %d | valor: %s" %
          (len(itens), ignoradas, brl(sum(i["valor_total"] for i in itens))))
    print("  gravado: %s" % a.saida)
    print("  Confira o mapeamento acima; se uma coluna estiver errada, repita com --mapa campo=COLUNA.")


# ---- custo conforme o regime -----------------------------------------------------------
CST_PIS_SEM_CREDITO = {"04", "05", "06", "07", "08", "09"}


def premissas_regime(a):
    r = a.regime
    icms = a.icms_recuperavel if a.icms_recuperavel else ("nao" if r == "simples" else "sim")
    pc = a.piscofins_recuperavel if a.piscofins_recuperavel else ("sim" if r == "real" else "nao")
    return {"regime": r, "icms_recuperavel": icms == "sim", "ipi_recuperavel": a.ipi_recuperavel == "sim",
            "piscofins_recuperavel": pc == "sim", "aliq_piscofins": dec(a.aliq_piscofins)}


def custo_entrada(m, pr):
    """Custo de aquisicao de uma linha de entrada (valor total da linha)."""
    if m["custo_informado"]:
        return m["custo_informado"]
    base = m["valor_produtos"] - m["desconto"] + m["frete"] + m["seguro"] + m["outras"] + m["ii"]
    custo = base + m["icms_st"]
    if not pr["ipi_recuperavel"]:
        custo += m["ipi"]
    icms_cred = Z
    if pr["icms_recuperavel"] and not m["icms_st"] and m["icms_cst"][-2:] not in {"60", "10", "30", "70"} \
            and m["icms_cst"] not in {"500", "201", "202", "203"}:
        icms_cred = m["icms"] + m["icms_cred_sn"]
        custo -= icms_cred
    if pr["piscofins_recuperavel"] and m["pis_cst"] not in CST_PIS_SEM_CREDITO:
        base_pc = base - icms_cred + (Z if pr["ipi_recuperavel"] else m["ipi"])
        custo -= (base_pc * pr["aliq_piscofins"] / 100).quantize(C2, rounding=ROUND_HALF_UP)
    return custo


# ---- apurar ----------------------------------------------------------------------------
def carregar_movimentos(caminho):
    movs = []
    for r in ler_csv(caminho):
        m = {c: r.get(c, "") for c in COLS_MOV}
        for c in COLS_NUM & set(COLS_MOV):
            m[c] = dec(m[c])
        m["data"] = data_br(m["data"])
        m["tipo"] = m["tipo"].upper()[:1]
        m["movimenta"] = (m["movimenta"] or "S").upper()[:1]
        if not m["natureza"]:
            m["natureza"] = "compra" if m["tipo"] == "E" else "venda"
        m["ean"] = ean_valido(m["ean"])
        movs.append(m)
    return movs


def carregar_depara(caminho):
    """depara.csv: cnpj_fornecedor;codigo_origem;codigo;fator  (cnpj vazio ou * = qualquer)."""
    dp = {}
    if caminho and os.path.exists(caminho):
        for r in ler_csv(caminho):
            if not r.get("codigo"):
                continue
            c = so_digitos(r.get("cnpj_fornecedor"))
            dp[(c, r.get("codigo_origem", ""))] = (r["codigo"], dec(r.get("fator")) or Decimal(1))
    return dp


def vincular(movs, cadastro, depara):
    """Preenche 'codigo' das entradas de terceiros. cadastro = produtos proprios conhecidos."""
    por_ean = {p["ean"]: p for p in cadastro.values() if p.get("ean")}
    por_desc = {}
    for p in cadastro.values():
        por_desc.setdefault(norm(p["descricao"]), p)
    descs = list(por_desc)
    pend, vistos, cont = [], set(), defaultdict(int)
    for m in movs:
        if m["movimenta"] != "S" or m["tipo"] != "E":
            continue
        if m["codigo"]:
            cont["ja_informado"] += 1
            m["fator"] = m["fator"] or Decimal(1)
            continue
        ch = (m["cnpj_participante"], m["codigo_origem"])
        alvo = depara.get(ch) or depara.get(("", m["codigo_origem"]))
        como = "depara"
        if not alvo and m["ean"] in por_ean:
            alvo, como = (por_ean[m["ean"]]["codigo"], Decimal(1)), "ean"
        if not alvo and norm(m["descricao"]) in por_desc:
            alvo, como = (por_desc[norm(m["descricao"])]["codigo"], Decimal(1)), "descricao"
        if alvo:
            m["codigo"], fator = alvo
            dest = cadastro.get(m["codigo"])
            if como != "depara" and dest and dest["unidade"] and dest["unidade"] != m["unidade"]:
                if m["unidade_trib"] == dest["unidade"] and m["quantidade"] and m["quantidade_trib"]:
                    fator = (m["quantidade_trib"] / m["quantidade"]).quantize(C6)
                    m["observacao"] = (m["observacao"] + "; " if m["observacao"] else "") + \
                        "fator %s pela unidade tributavel (%s->%s)" % (fmt(fator), m["unidade"], dest["unidade"])
                else:
                    m["observacao"] = (m["observacao"] + "; " if m["observacao"] else "") + \
                        "UNIDADE DIFERENTE (%s x %s): informar fator no depara" % (m["unidade"], dest["unidade"])
                    if ch not in vistos:
                        vistos.add(ch)
                        pend.append({"tipo": "unidade", "cnpj_fornecedor": ch[0], "fornecedor": m["participante"],
                                     "codigo_origem": ch[1], "descricao": m["descricao"], "unidade": m["unidade"],
                                     "codigo_item": m["codigo"], "detalhe": "produto proprio em %s" % dest["unidade"]})
            m["fator"] = fator
            cont[como] += 1
        else:
            m["codigo"] = m["ean"] or "F%s-%s" % (m["cnpj_participante"][:8], m["codigo_origem"])
            m["fator"] = Decimal(1)
            cont["sem_vinculo"] += 1
            if ch not in vistos and cadastro:
                vistos.add(ch)
                sug = difflib.get_close_matches(norm(m["descricao"]), descs, n=3, cutoff=0.6)
                pend.append({"tipo": "vinculo", "cnpj_fornecedor": ch[0], "fornecedor": m["participante"],
                             "codigo_origem": ch[1], "descricao": m["descricao"], "unidade": m["unidade"],
                             "codigo_item": por_desc[sug[0]]["codigo"] if sug else "",
                             "detalhe": " | ".join("%s=%s" % (por_desc[s]["codigo"], por_desc[s]["descricao"]) for s in sug)})
    return pend, cont


def montar_cadastro(movs, inicial, contagem=None):
    cad = {}
    for it in (inicial or []) + (contagem or []):
        if it["codigo"]:
            cad.setdefault(it["codigo"], {"codigo": it["codigo"], "descricao": it["descricao"], "ncm": it["ncm"],
                                          "unidade": it["unidade"], "ean": it["ean"], "grupo": it.get("grupo", "00")})
    for m in movs:
        if m["tipo"] == "S" and m["codigo"] and m["movimenta"] != "N":
            c = cad.setdefault(m["codigo"], {"codigo": m["codigo"], "descricao": m["descricao"], "ncm": m["ncm"],
                                             "unidade": m["unidade"], "ean": m["ean"], "grupo": "00"})
            c["ean"] = c["ean"] or m["ean"]
            c["ncm"] = c["ncm"] or m["ncm"]
    return cad


def kardex(movs, inicial, pr, data_fim, cadastro=None):
    """Custo medio ponderado movel, item a item. Devolve (itens, ficha, pendencias)."""
    est = {}
    ficha, pend = [], []
    for it in inicial or []:
        est[it["codigo"]] = {"q": it["quantidade"], "v": it["valor_total"], "cm": it["custo_unitario"],
                             "desc": it["descricao"], "ncm": it["ncm"], "un": it["unidade"], "ean": it["ean"],
                             "grupo": it.get("grupo", "00"), "min": it["quantidade"], "ent": Z, "sai": Z,
                             "ult": it["custo_unitario"], "sem_custo": False}
        ficha.append({"codigo": it["codigo"], "data": "", "documento": "SALDO INICIAL", "natureza": "inicial",
                      "entrada": it["quantidade"], "saida": "", "custo_mov": it["valor_total"],
                      "saldo_qtd": it["quantidade"], "saldo_valor": it["valor_total"], "custo_medio": it["custo_unitario"]})
    ordem = sorted([m for m in movs if m["movimenta"] == "S" and (not data_fim or not m["data"] or m["data"] <= data_fim)],
                   key=lambda m: (m["data"] or dt.date.min, 0 if m["tipo"] == "E" else 1))
    for m in ordem:
        cd = (cadastro or {}).get(m["codigo"]) or {}
        e = est.setdefault(m["codigo"], {"q": Z, "v": Z, "cm": Z, "desc": cd.get("descricao") or m["descricao"],
                                         "ncm": cd.get("ncm") or m["ncm"], "un": cd.get("unidade") or m["unidade"],
                                         "ean": cd.get("ean") or m["ean"], "grupo": cd.get("grupo", "00"), "min": Z,
                                         "ent": Z, "sai": Z, "ult": Z, "sem_custo": False})
        e["ncm"] = e["ncm"] or m["ncm"]
        fator = m["fator"] or Decimal(1)
        q = m["quantidade"] * fator
        if m["tipo"] == "E":
            if m["natureza"] == "devolucao_venda":
                valor = (q * e["cm"]).quantize(C2) if e["cm"] else Z
                if not e["cm"]:
                    e["sem_custo"] = True
            else:
                valor = custo_entrada(m, pr)
                if q:
                    e["ult"] = (valor / q).quantize(C6, rounding=ROUND_HALF_UP)
            if e["q"] < 0:  # vinha negativo: recomeca pelo custo desta entrada
                e["q"] += q
                e["v"] = (e["q"] * (valor / q if q else e["cm"])).quantize(C2) if q else e["v"]
            else:
                e["q"] += q
                e["v"] += valor
            e["ent"] += q
            if e["q"] > 0:
                e["cm"] = (e["v"] / e["q"]).quantize(C6, rounding=ROUND_HALF_UP)
            ficha.append({"codigo": m["codigo"], "data": m["data"], "documento": "%s %s" % (m["modelo"] or "NF", m["numero"]),
                          "natureza": m["natureza"], "entrada": q, "saida": "", "custo_mov": valor,
                          "saldo_qtd": e["q"], "saldo_valor": e["v"], "custo_medio": e["cm"]})
        else:
            if not e["cm"]:
                e["sem_custo"] = True
            valor = (q * e["cm"]).quantize(C2, rounding=ROUND_HALF_UP)
            e["q"] -= q
            e["v"] = e["v"] - valor if e["q"] > 0 else (e["q"] * e["cm"]).quantize(C2)
            e["sai"] += q
            e["min"] = min(e["min"], e["q"])
            ficha.append({"codigo": m["codigo"], "data": m["data"], "documento": "%s %s" % (m["modelo"] or "NF", m["numero"]),
                          "natureza": m["natureza"], "entrada": "", "saida": q, "custo_mov": valor,
                          "saldo_qtd": e["q"], "saldo_valor": e["v"], "custo_medio": e["cm"]})
    itens = []
    for cod, e in sorted(est.items()):
        obs = []
        if e["min"] < 0:
            pend.append({"tipo": "saldo_negativo", "codigo_item": cod, "descricao": e["desc"], "unidade": e["un"],
                         "detalhe": "menor saldo %s | entradas %s | saidas %s | saldo final %s" %
                                    (fmt(e["min"], 3), fmt(e["ent"], 3), fmt(e["sai"], 3), fmt(e["q"], 3))})
            obs.append("teve saldo negativo no periodo")
        if e["sem_custo"]:
            pend.append({"tipo": "sem_custo", "codigo_item": cod, "descricao": e["desc"], "unidade": e["un"],
                         "detalhe": "saida/devolucao sem entrada anterior para dar custo"})
        if e["q"] <= 0:
            continue
        q = e["q"].quantize(C3, rounding=ROUND_HALF_UP)
        itens.append({"codigo": cod, "descricao": e["desc"], "ncm": so_digitos(e["ncm"]), "unidade": e["un"] or "UN",
                      "quantidade": q, "custo_unitario": e["cm"], "valor_total": (q * e["cm"]).quantize(C2, rounding=ROUND_HALF_UP),
                      "grupo": e["grupo"], "ean": e["ean"], "observacao": "; ".join(obs)})
    return itens, ficha, pend


def custos_por_item(movs, pr, criterio):
    """Custo unitario de cada item pelas entradas: 'medio' do periodo ou 'ultima' compra."""
    ac = defaultdict(lambda: [Z, Z, Z, None])  # qtd, valor, ultimo custo, ref
    for m in sorted(movs, key=lambda m: m["data"] or dt.date.min):
        if m["movimenta"] != "S" or m["tipo"] != "E" or m["natureza"] == "devolucao_venda":
            continue
        q = m["quantidade"] * (m["fator"] or Decimal(1))
        if not q:
            continue
        v = custo_entrada(m, pr)
        a = ac[m["codigo"]]
        a[0] += q
        a[1] += v
        a[2] = (v / q).quantize(C6, rounding=ROUND_HALF_UP)
        a[3] = m
    return {c: ((a[1] / a[0]).quantize(C6, rounding=ROUND_HALF_UP) if criterio == "medio" else a[2], a[3])
            for c, a in ac.items()}


UN_INTEIRAS = {"UN", "UND", "UNID", "PC", "PCA", "PECA", "PÇ", "CX", "CXA", "FD", "PCT", "PAR", "JG", "KIT", "DZ", "FR", "LT", "SC"}


def apurar_contagem(contagem, movs, pr, criterio):
    custos = custos_por_item(movs, pr, "medio" if criterio == "planilha" else criterio) if movs else {}
    ref_ean, ref_desc = {}, {}
    for cod, (cu, m) in custos.items():
        if m["ean"]:
            ref_ean.setdefault(m["ean"], cod)
        ref_desc.setdefault(norm(m["descricao"]), cod)
    descs = list(ref_desc)
    itens, pend = [], []
    for it in contagem:
        it = dict(it)
        cu, como = Z, ""
        if criterio == "planilha" and it["custo_unitario"]:
            cu, como = it["custo_unitario"], "custo da planilha"
        else:
            cod = it["codigo"] if it["codigo"] in custos else ref_ean.get(it["ean"]) or ref_desc.get(norm(it["descricao"]))
            if cod:
                cu, m = custos[cod]
                como = "custo %s das entradas" % criterio
                it["ncm"] = it["ncm"] or so_digitos(m["ncm"])
        if not cu:
            if it["custo_unitario"]:
                cu, como = it["custo_unitario"], "custo da planilha (sem nota de entrada)"
            else:
                sug = difflib.get_close_matches(norm(it["descricao"]), descs, n=3, cutoff=0.55)
                pend.append({"tipo": "sem_custo", "codigo_item": it["codigo"], "descricao": it["descricao"],
                             "unidade": it["unidade"],
                             "detalhe": "sem entrada correspondente. Parecidos: " +
                                        " | ".join("%s (%s)" % (custos[ref_desc[s]][1]["descricao"], fmt(custos[ref_desc[s]][0], 4)) for s in sug)})
        it["custo_unitario"] = cu
        it["valor_total"] = (it["quantidade"] * cu).quantize(C2, rounding=ROUND_HALF_UP)
        it["observacao"] = como or "SEM CUSTO"
        itens.append(it)
    return itens, pend


def apurar_alvo(movs, pr, alvo, criterio, base, exato, cadastro=None):
    itens, sobra = [], alvo
    if criterio == "proporcional":
        total = sum(i["valor_total"] for i in base)
        if not total:
            sys.exit("ERRO: a base (--base) esta sem valor.")
        k = alvo / total
        for it in base:
            it = dict(it)
            q = it["quantidade"] * k
            q = q.quantize(C3) if exato or it["unidade"] not in UN_INTEIRAS else q.quantize(Decimal(1), rounding=ROUND_HALF_UP)
            if q <= 0:
                continue
            it["quantidade"], it["valor_total"] = q, (q * it["custo_unitario"]).quantize(C2, rounding=ROUND_HALF_UP)
            it["observacao"] = "proporcional a base (fator %s)" % fmt(k, 4)
            itens.append(it)
        return itens
    ac = {}
    ent = [m for m in movs if m["movimenta"] == "S" and m["tipo"] == "E" and m["natureza"] in ("compra", "bonificacao", "transf_entrada")]
    for m in sorted(ent, key=lambda m: m["data"] or dt.date.min, reverse=True):
        if sobra <= 0:
            break
        q = m["quantidade"] * (m["fator"] or Decimal(1))
        if q <= 0:
            continue
        v = custo_entrada(m, pr)
        cu = v / q
        if cu <= 0:
            continue
        cd = (cadastro or {}).get(m["codigo"]) or {}
        un = cd.get("unidade") or m["unidade"] or "UN"
        if v > sobra:
            inteiro = not exato and (un in UN_INTEIRAS or q == q.to_integral_value())
            q = (sobra / cu).quantize(Decimal(1) if inteiro else C3, rounding=ROUND_DOWN)
            if q <= 0:
                continue
            v = (q * cu).quantize(C2, rounding=ROUND_HALF_UP)
        a = ac.setdefault(m["codigo"], {"codigo": m["codigo"], "descricao": cd.get("descricao") or m["descricao"],
                                        "ncm": so_digitos(cd.get("ncm") or m["ncm"]), "unidade": un, "quantidade": Z,
                                        "valor_total": Z, "grupo": cd.get("grupo", "00"), "ean": cd.get("ean") or m["ean"], "nfs": []})
        a["quantidade"] += q
        a["valor_total"] += v
        a["nfs"].append(m["numero"])
        sobra -= v
    for a in ac.values():
        a["custo_unitario"] = (a["valor_total"] / a["quantidade"]).quantize(C6, rounding=ROUND_HALF_UP)
        a["valor_total"] = a["valor_total"].quantize(C2, rounding=ROUND_HALF_UP)
        a["observacao"] = "ultimas compras: NF " + ", ".join(dict.fromkeys(a.pop("nfs")))[:80]
        itens.append(a)
    return sorted(itens, key=lambda i: i["codigo"])


def cmd_apurar(a):
    pr = premissas_regime(a)
    data_fim = data_br(a.data) if a.data else None
    movs = carregar_movimentos(a.movimentos) if a.movimentos else []
    inicial = ler_inventario(a.inicial) if a.inicial else []
    contagem = ler_inventario(a.contagem) if a.contagem else []
    if data_fim:
        movs = [m for m in movs if not m["data"] or m["data"] <= data_fim]
    excl = {so_digitos(c) for c in (a.excluir_fornecedores or "").split(",") if c.strip()}
    for m in movs:
        if m["tipo"] == "E" and m["cnpj_participante"] in excl:
            m["movimenta"], m["observacao"] = "N", "fornecedor excluido (uso/consumo ou imobilizado)"
    cadastro = montar_cadastro(movs, inicial, contagem)
    pend, cont = vincular(movs, cadastro, carregar_depara(a.depara))
    ficha = []
    if a.metodo == "movimentacao":
        if not movs:
            sys.exit("ERRO: o metodo 'movimentacao' precisa de --movimentos.")
        itens, ficha, p2 = kardex(movs, inicial, pr, data_fim, cadastro)
        pend += p2
    elif a.metodo == "contagem":
        if not contagem:
            sys.exit("ERRO: o metodo 'contagem' precisa de --contagem (CSV gerado por ler-planilha).")
        itens, p2 = apurar_contagem(contagem, movs, pr, a.custo)
        pend += p2
    else:
        if a.alvo is None:
            sys.exit("ERRO: o metodo 'alvo' precisa de --alvo VALOR.")
        base = ler_inventario(a.base) if a.base else []
        if a.criterio == "proporcional" and not base:
            sys.exit("ERRO: o criterio 'proporcional' precisa de --base inventario.csv.")
        itens = apurar_alvo(movs, pr, dec(a.alvo), a.criterio, base, a.exato, cadastro)
    total = sum(i["valor_total"] for i in itens)
    os.makedirs(a.saida, exist_ok=True)
    gravar_csv(os.path.join(a.saida, "inventario.csv"), COLS_INV, itens)
    gravar_csv(os.path.join(a.saida, "pendencias.csv"),
               ["tipo", "cnpj_fornecedor", "fornecedor", "codigo_origem", "descricao", "unidade", "codigo_item", "detalhe"], pend)
    if ficha:
        gravar_csv(os.path.join(a.saida, "ficha_movimentacao.csv"),
                   ["codigo", "data", "documento", "natureza", "entrada", "saida", "custo_mov", "saldo_qtd", "saldo_valor", "custo_medio"],
                   sorted(ficha, key=lambda f: f["codigo"]))
    if movs:
        gravar_csv(os.path.join(a.saida, "movimentos_vinculados.csv"), COLS_MOV, movs)
    compras = sum(custo_entrada(m, pr) for m in movs if m["movimenta"] == "S" and m["tipo"] == "E" and m["natureza"] != "devolucao_venda")
    compras -= sum(f["custo_mov"] for f in ficha if f["natureza"] == "devolucao_compra")
    vendas = sum(m["valor_produtos"] - m["desconto"] for m in movs if m["movimenta"] == "S" and m["natureza"] == "venda")
    ini = sum(i["valor_total"] for i in inicial)
    prem = {"metodo": a.metodo, "data_inventario": a.data or "", "regime": pr["regime"],
            "icms_recuperavel": pr["icms_recuperavel"], "ipi_recuperavel": pr["ipi_recuperavel"],
            "piscofins_recuperavel": pr["piscofins_recuperavel"], "aliq_piscofins": str(pr["aliq_piscofins"]),
            "criterio_custo": "medio ponderado movel" if a.metodo == "movimentacao" else (a.custo if a.metodo == "contagem" else a.criterio),
            "estoque_inicial": str(ini), "compras_a_custo": str(compras), "vendas": str(vendas),
            "estoque_final": str(total), "cmv": str(ini + compras - total) if movs else "",
            "valor_alvo": str(dec(a.alvo)) if a.alvo is not None else "",
            "itens": len(itens), "pendencias": len(pend), "vinculos": dict(cont)}
    with open(os.path.join(a.saida, "premissas.json"), "w", encoding="utf-8") as f:
        json.dump(prem, f, ensure_ascii=False, indent=2)

    print("APURACAO DO ESTOQUE - metodo: %s | regime: %s" % (a.metodo, pr["regime"]))
    print("  custo: ICMS %s | IPI %s | PIS/COFINS %s" % (
        "recuperavel (fora do custo)" if pr["icms_recuperavel"] else "no custo",
        "recuperavel (fora do custo)" if pr["ipi_recuperavel"] else "no custo",
        "recuperavel a %s%% (fora do custo)" % fmt(pr["aliq_piscofins"]) if pr["piscofins_recuperavel"] else "no custo"))
    if cont:
        print("  vinculo das entradas: " + ", ".join("%s=%d" % kv for kv in sorted(cont.items())))
    print("  itens no inventario : %d" % len(itens))
    if movs:
        print("  estoque inicial     : %15s" % brl(ini))
        print("  (+) compras liquidas: %15s" % brl(compras))
        print("  (-) estoque final   : %15s" % brl(total))
        cmv = ini + compras - total
        print("  (=) CMV             : %15s" % brl(cmv))
        if vendas:
            print("  vendas (liq. desc.) : %15s  | CMV/vendas: %s%%" % (brl(vendas), fmt(cmv / vendas * 100, 1)))
            if cmv < 0 or cmv > vendas:
                print("  ATENCAO: CMV fora do razoavel (negativo ou maior que as vendas). Revise vinculos, unidades e notas faltantes.")
    else:
        print("  estoque final       : %15s" % brl(total))
    if a.alvo is not None:
        print("  valor alvo          : %15s  | diferenca: %s" % (brl(dec(a.alvo)), brl(total - dec(a.alvo))))
    tipos = defaultdict(int)
    for p in pend:
        tipos[p["tipo"]] += 1
    if pend:
        print("  PENDENCIAS: " + ", ".join("%s=%d" % kv for kv in sorted(tipos.items())) + " (ver pendencias.csv)")
    print("  gravado em: %s" % a.saida)


# ---- conferir ---------------------------------------------------------------------------
def conferir(itens):
    erros, avisos, vistos = [], [], {}
    for n, i in enumerate(itens, 2):
        ref = "linha %d (%s %s)" % (n, i["codigo"], i["descricao"][:30])
        if not i["codigo"]:
            erros.append(ref + ": sem codigo")
        elif i["codigo"] in vistos:
            erros.append(ref + ": codigo repetido (tambem na linha %d)" % vistos[i["codigo"]])
        vistos.setdefault(i["codigo"], n)
        if not i["descricao"]:
            erros.append(ref + ": sem descricao")
        if i["quantidade"] <= 0:
            erros.append(ref + ": quantidade zero ou negativa")
        if i["custo_unitario"] <= 0:
            erros.append(ref + ": sem custo unitario")
        if abs(i["valor_total"] - (i["quantidade"] * i["custo_unitario"]).quantize(C2, rounding=ROUND_HALF_UP)) > Decimal("0.02"):
            avisos.append(ref + ": total difere de quantidade x custo")
        if len(i["ncm"]) != 8:
            avisos.append(ref + ": NCM ausente ou com tamanho diferente de 8")
        if not i["unidade"]:
            avisos.append(ref + ": sem unidade")
    return erros, avisos


def cmd_conferir(a):
    itens = ler_inventario(a.inventario)
    erros, avisos = conferir(itens)
    print("CONFERENCIA: %d itens | total %s" % (len(itens), brl(sum(i["valor_total"] for i in itens))))
    for t, lst in (("ERRO", erros), ("AVISO", avisos)):
        for e in lst[:60]:
            print("  %s: %s" % (t, e))
        if len(lst) > 60:
            print("  ... e mais %d %s(s)" % (len(lst) - 60, t.lower()))
    print("  resultado: %s" % ("COM ERROS - corrija antes de gerar" if erros else "OK" + (" (com avisos)" if avisos else "")))
    return 1 if erros else 0


def cmd_gerar(a):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import saidas
    itens = ler_inventario(a.inventario)
    erros, avisos = conferir(itens)
    if erros and not a.forcar:
        for e in erros[:40]:
            print("  ERRO: " + e)
        sys.exit("Inventario com %d erro(s). Corrija (ou use --forcar depois de avisar o usuario)." % len(erros))
    saidas.gerar(a, itens, avisos)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("ler-xml", help="le XMLs de NF-e/NFC-e")
    s.add_argument("origens", nargs="+", help="pastas, arquivos .xml ou .zip")
    s.add_argument("--cnpj", required=True, help="CNPJ da empresa do inventario")
    s.add_argument("--de", type=data_br, help="data inicial dd/mm/aaaa")
    s.add_argument("--ate", type=data_br, help="data final dd/mm/aaaa")
    s.add_argument("--saida", required=True, help="pasta de trabalho")
    s.set_defaults(f=cmd_ler_xml)

    s = sub.add_parser("ler-planilha", help="planilha/relatorio -> inventario padrao")
    s.add_argument("arquivo")
    s.add_argument("--saida", required=True, help="CSV de saida")
    s.add_argument("--aba")
    s.add_argument("--linha-cabecalho", type=int)
    s.add_argument("--mapa", action="append", help="campo=COLUNA (letra ou nome do cabecalho); pode repetir")
    s.add_argument("--manter-zerados", action="store_true")
    s.set_defaults(f=cmd_ler_planilha)

    s = sub.add_parser("apurar", help="calcula o inventario")
    s.add_argument("--metodo", required=True, choices=["movimentacao", "alvo", "contagem"])
    s.add_argument("--regime", required=True, choices=["simples", "presumido", "real"])
    s.add_argument("--movimentos", help="movimentos.csv")
    s.add_argument("--inicial", help="inventario anterior (CSV padrao)")
    s.add_argument("--contagem", help="contagem do cliente (CSV padrao)")
    s.add_argument("--depara", help="depara.csv de codigos do fornecedor")
    s.add_argument("--data", help="data do inventario dd/mm/aaaa (ignora notas posteriores)")
    s.add_argument("--custo", default="medio", choices=["medio", "ultima", "planilha"], help="metodo contagem")
    s.add_argument("--alvo", help="valor total desejado (metodo alvo)")
    s.add_argument("--criterio", default="ultimas-compras", choices=["ultimas-compras", "proporcional"])
    s.add_argument("--base", help="inventario base para o criterio proporcional")
    s.add_argument("--exato", action="store_true", help="aceita quantidade fracionada para chegar mais perto do alvo")
    s.add_argument("--excluir-fornecedores", help="CNPJs (virgula) cujas compras nao sao estoque")
    s.add_argument("--icms-recuperavel", choices=["sim", "nao"])
    s.add_argument("--ipi-recuperavel", choices=["sim", "nao"], default="nao")
    s.add_argument("--piscofins-recuperavel", choices=["sim", "nao"])
    s.add_argument("--aliq-piscofins", default="9.25")
    s.add_argument("--saida", required=True, help="pasta de trabalho")
    s.set_defaults(f=cmd_apurar)

    s = sub.add_parser("conferir", help="valida um inventario.csv")
    s.add_argument("inventario")
    s.set_defaults(f=cmd_conferir)

    s = sub.add_parser("gerar", help="gera Excel, Livro (PDF) e arquivo do Dominio")
    s.add_argument("inventario")
    s.add_argument("--empresa", required=True, help="razao social")
    s.add_argument("--cnpj", required=True)
    s.add_argument("--ie", default="")
    s.add_argument("--codigo-empresa", default="", help="codigo da empresa no Dominio")
    s.add_argument("--data", required=True, help="data do inventario dd/mm/aaaa")
    s.add_argument("--formatos", default="excel,livro,dominio", help="excel,livro,dominio,sped")
    s.add_argument("--modelo-dominio", help="planilha modelo baixada do Dominio (.xlsx)")
    s.add_argument("--premissas", help="premissas.json da apuracao (entra na aba Resumo)")
    s.add_argument("--pasta-trabalho", help="pasta da apuracao (pendencias e ficha entram no Excel)")
    s.add_argument("--uf", default="", help="UF (arquivo SPED)")
    s.add_argument("--cod-mun", default="", help="codigo IBGE do municipio (arquivo SPED)")
    s.add_argument("--motivo", default="01", help="MOT_INV do H005 (01 = final do periodo)")
    s.add_argument("--forcar", action="store_true")
    s.add_argument("--saida", required=True)
    s.set_defaults(f=cmd_gerar)

    a = p.parse_args()
    sys.exit(a.f(a) or 0)


if __name__ == "__main__":
    main()
