# -*- coding: utf-8 -*-
"""Saidas do estoque fiscal: Excel, Livro Registro de Inventario (PDF), Dominio e SPED Bloco H."""
import csv
import datetime as dt
import json
import os
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

from estoque import (brl, fmt, so_digitos, data_br, ler_csv, mapear_cabecalho, norm, C2)

GRUPOS = {"00": "Mercadorias para revenda", "01": "Matérias-primas", "02": "Embalagens",
          "03": "Produtos em processo", "04": "Produtos acabados", "05": "Subprodutos",
          "06": "Produtos intermediários", "07": "Material de uso e consumo", "08": "Ativo imobilizado",
          "10": "Outros insumos", "99": "Outras"}
ROTULO_PREMISSA = [
    ("metodo", "Método de apuração"), ("criterio_custo", "Critério de custo"), ("regime", "Regime tributário"),
    ("icms_recuperavel", "ICMS recuperável (fora do custo)"), ("ipi_recuperavel", "IPI recuperável (fora do custo)"),
    ("piscofins_recuperavel", "PIS/COFINS recuperáveis (fora do custo)"), ("aliq_piscofins", "Alíquota PIS+COFINS (%)"),
    ("estoque_inicial", "Estoque inicial"), ("compras_a_custo", "Compras a custo"), ("estoque_final", "Estoque final"),
    ("cmv", "CMV (inicial + compras - final)"), ("vendas", "Vendas (líquidas de desconto)"),
    ("valor_alvo", "Valor alvo informado"), ("pendencias", "Pendências em aberto")]


def cnpj_fmt(c):
    c = so_digitos(c)
    return "%s.%s.%s/%s-%s" % (c[:2], c[2:5], c[5:8], c[8:12], c[12:]) if len(c) == 14 else c


def _f(d):
    return float(Decimal(d))


def gerar_excel(a, itens, data, base, premissas, avisos):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
    wb = Workbook()
    ws = wb.active
    ws.title = "Inventário"
    neg, cinza = Font(bold=True), PatternFill("solid", fgColor="D9D9D9")
    ws["A1"], ws["A2"] = "REGISTRO DE INVENTÁRIO - %s" % a.empresa, "CNPJ %s   IE %s   Estoques existentes em %s" % (
        cnpj_fmt(a.cnpj), a.ie or "-", data.strftime("%d/%m/%Y"))
    ws["A1"].font = Font(bold=True, size=13)
    cab = ["Código", "Descrição", "NCM", "Unidade", "Quantidade", "Custo unitário", "Valor total", "Grupo", "EAN", "Observação"]
    for c, t in enumerate(cab, 1):
        cel = ws.cell(row=4, column=c, value=t)
        cel.font, cel.fill, cel.alignment = neg, cinza, Alignment(horizontal="center")
    for r, i in enumerate(itens, 5):
        ws.append([i["codigo"], i["descricao"], i["ncm"], i["unidade"], _f(i["quantidade"]), _f(i["custo_unitario"]),
                   _f(i["valor_total"]), GRUPOS.get(i["grupo"], i["grupo"]), i["ean"], i["observacao"]])
        ws.cell(row=r, column=5).number_format = "#,##0.000"
        ws.cell(row=r, column=6).number_format = "#,##0.0000"
        ws.cell(row=r, column=7).number_format = "#,##0.00"
    fim = 4 + len(itens)
    ws.cell(row=fim + 1, column=2, value="TOTAL").font = neg
    tot = ws.cell(row=fim + 1, column=7, value="=SUM(G5:G%d)" % fim if itens else 0)
    tot.font, tot.number_format = neg, "#,##0.00"
    for c, w in enumerate([16, 52, 11, 9, 13, 15, 15, 24, 15, 44], 1):
        ws.column_dimensions[get_column_letter(c)].width = w
    ws.freeze_panes = "A5"
    ws.auto_filter.ref = "A4:J%d" % max(fim, 4)

    rs = wb.create_sheet("Resumo")
    rs.append(["Empresa", a.empresa])
    rs.append(["CNPJ", cnpj_fmt(a.cnpj)])
    rs.append(["Data do inventário", data.strftime("%d/%m/%Y")])
    rs.append(["Itens", len(itens)])
    rs.append(["Valor total", _f(sum(i["valor_total"] for i in itens))])
    rs["B5"].number_format = "#,##0.00"
    rs.append([])
    rs.append(["PREMISSAS DA APURAÇÃO"])
    rs["A7"].font = neg
    for k, rot in ROTULO_PREMISSA:
        v = premissas.get(k, "")
        if v == "" or v is None:
            continue
        if isinstance(v, bool):
            v = "Sim" if v else "Não"
        elif k in ("estoque_inicial", "compras_a_custo", "estoque_final", "cmv", "vendas", "valor_alvo"):
            v = _f(v)
        rs.append([rot, v])
        if isinstance(v, float):
            rs.cell(row=rs.max_row, column=2).number_format = "#,##0.00"
    rs.append([])
    rs.append(["POR GRUPO"])
    rs.cell(row=rs.max_row, column=1).font = neg
    grp = defaultdict(lambda: [0, Decimal(0)])
    for i in itens:
        grp[i["grupo"]][0] += 1
        grp[i["grupo"]][1] += i["valor_total"]
    for g in sorted(grp):
        rs.append([GRUPOS.get(g, g), _f(grp[g][1]), "%d itens" % grp[g][0]])
        rs.cell(row=rs.max_row, column=2).number_format = "#,##0.00"
    if avisos:
        rs.append([])
        rs.append(["AVISOS DA CONFERÊNCIA (%d)" % len(avisos)])
        rs.cell(row=rs.max_row, column=1).font = neg
        for av in avisos[:200]:
            rs.append([av])
    rs.column_dimensions["A"].width, rs.column_dimensions["B"].width = 44, 24

    pasta = a.pasta_trabalho
    for nome, aba in (("pendencias.csv", "Pendências"), ("ficha_movimentacao.csv", "Ficha de movimentação")):
        arq = os.path.join(pasta, nome) if pasta else ""
        if not arq or not os.path.exists(arq):
            continue
        with open(arq, "r", encoding="utf-8-sig", newline="") as f:
            linhas = list(csv.reader(f, delimiter=";"))
        if len(linhas) < 2:
            continue
        sh = wb.create_sheet(aba)
        for n, l in enumerate(linhas):
            if n and nome.startswith("ficha"):
                l = l[:4] + [(_f(x.replace(",", ".")) if x else None) for x in l[4:]]
            sh.append(l)
        for c in sh[1]:
            c.font, c.fill = neg, cinza
        for c in range(1, sh.max_column + 1):
            sh.column_dimensions[get_column_letter(c)].width = 18
        sh.freeze_panes = "A2"
    caminho = os.path.join(a.saida, base + "_inventario.xlsx")
    wb.save(caminho)
    return caminho


def gerar_livro(a, itens, data, base):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, LongTable, TableStyle, Paragraph, Spacer

    caminho = os.path.join(a.saida, base + "_livro_registro_inventario.pdf")
    peq = ParagraphStyle("p", fontName="Helvetica", fontSize=7.5, leading=9)
    dirt = ParagraphStyle("d", parent=peq, alignment=2)
    neg = ParagraphStyle("n", parent=peq, fontName="Helvetica-Bold")
    negd = ParagraphStyle("nd", parent=neg, alignment=2)

    def cabecalho(c, doc):
        c.saveState()
        w, h = landscape(A4)
        c.setFont("Helvetica-Bold", 13)
        c.drawCentredString(w / 2, h - 12 * mm, "REGISTRO DE INVENTÁRIO")
        c.setFont("Helvetica", 8.5)
        c.drawString(12 * mm, h - 19 * mm, "Firma: %s" % a.empresa)
        c.drawString(12 * mm, h - 24 * mm, "CNPJ: %s     Inscrição Estadual: %s" % (cnpj_fmt(a.cnpj), a.ie or "-"))
        c.drawRightString(w - 12 * mm, h - 19 * mm, "Folha: %d" % doc.page)
        c.drawRightString(w - 12 * mm, h - 24 * mm, "Estoques existentes em: %s" % data.strftime("%d/%m/%Y"))
        c.line(12 * mm, h - 26 * mm, w - 12 * mm, h - 26 * mm)
        c.setFont("Helvetica", 6.5)
        c.drawString(12 * mm, 7 * mm, "Modelo P7 - valores em reais")
        c.restoreState()

    dados = [[Paragraph(t, neg) for t in ("Classificação fiscal", "Discriminação", "Unid.", "Quantidade",
                                          "Valor unitário", "Valor parcial", "Valor total", "Observações")]]
    estilo = [("GRID", (0, 0), (-1, -1), 0.3, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
              ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 1.5),
              ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5)]
    grupos = defaultdict(list)
    for i in itens:
        grupos[i["grupo"]].append(i)
    geral = Decimal(0)
    for g in sorted(grupos):
        dados.append([Paragraph(GRUPOS.get(g, g).upper(), neg)] + [""] * 7)
        estilo += [("SPAN", (0, len(dados) - 1), (-1, len(dados) - 1)), ("BACKGROUND", (0, len(dados) - 1), (-1, len(dados) - 1), colors.whitesmoke)]
        sub = Decimal(0)
        for i in sorted(grupos[g], key=lambda x: (x["ncm"], x["descricao"])):
            sub += i["valor_total"]
            ncm = i["ncm"]
            ncm = "%s.%s.%s" % (ncm[:4], ncm[4:6], ncm[6:]) if len(ncm) == 8 else ncm
            dados.append([Paragraph(ncm, peq), Paragraph("%s - %s" % (i["codigo"], i["descricao"]), peq),
                          Paragraph(i["unidade"], peq), Paragraph(fmt(i["quantidade"], 3), dirt),
                          Paragraph(fmt(i["custo_unitario"], 4), dirt), Paragraph(brl(i["valor_total"]), dirt), "", ""])
        dados.append(["", Paragraph("Total de %s" % GRUPOS.get(g, g).lower(), neg), "", "", "", "", Paragraph(brl(sub), negd), ""])
        geral += sub
    dados.append(["", Paragraph("TOTAL GERAL DO INVENTÁRIO", neg), "", "", "", "", Paragraph(brl(geral), negd), ""])
    estilo.append(("BACKGROUND", (0, len(dados) - 1), (-1, len(dados) - 1), colors.lightgrey))
    tab = LongTable(dados, colWidths=[24 * mm, 104 * mm, 13 * mm, 24 * mm, 26 * mm, 28 * mm, 30 * mm, 24 * mm], repeatRows=1)
    tab.setStyle(TableStyle(estilo))
    doc = SimpleDocTemplate(caminho, pagesize=landscape(A4), leftMargin=12 * mm, rightMargin=12 * mm,
                            topMargin=29 * mm, bottomMargin=12 * mm, title="Registro de Inventário - %s" % a.empresa)
    doc.build([tab, Spacer(1, 6 * mm)], onFirstPage=cabecalho, onLaterPages=cabecalho)
    return caminho


CAMPOS_DOMINIO = [("codigo", "Código"), ("descricao", "Descrição"), ("ncm", "NCM"), ("unidade", "Unidade"),
                  ("quantidade", "Quantidade"), ("custo_unitario", "Valor unitário"), ("valor_total", "Valor total")]


def _valor_dominio(i, campo):
    v = i[campo]
    return _f(v) if campo in ("quantidade", "custo_unitario", "valor_total") else v


def gerar_dominio(a, itens, data, base):
    """Preenche a planilha modelo do Dominio; sem modelo, gera uma planilha generica (a conferir)."""
    import openpyxl
    arquivos, avisos = [], []
    if a.modelo_dominio:
        if a.modelo_dominio.lower().endswith(".xls"):
            raise SystemExit("ERRO: o modelo esta em .xls. Abra no Excel, salve como .xlsx e informe de novo.")
        wb = openpyxl.load_workbook(a.modelo_dominio)
        ws = wb.worksheets[0]
        ih, mapa = 1, {}
        for r in range(1, min(ws.max_row, 40) + 1):
            m = mapear_cabecalho([ws.cell(row=r, column=c).value or "" for c in range(1, ws.max_column + 1)])
            if len(m) > len(mapa):
                ih, mapa = r, m
        if "quantidade" not in mapa or "codigo" not in mapa:
            raise SystemExit("ERRO: nao reconheci as colunas da planilha modelo (codigo/quantidade). "
                             "Abra o modelo, veja o cabecalho e preencha a planilha manualmente a partir do inventario.xlsx.")
        cab = [str(ws.cell(row=ih, column=c).value or "").strip() for c in range(1, ws.max_column + 1)]
        for r in range(ih + 1, ws.max_row + 1):  # limpa linhas de exemplo do modelo
            for c in range(1, ws.max_column + 1):
                ws.cell(row=r, column=c).value = None
        for n, i in enumerate(itens):
            for campo, col in mapa.items():
                if campo in i:
                    ws.cell(row=ih + 1 + n, column=col + 1, value=_valor_dominio(i, campo))
        usadas = set(mapa.values())
        print("  Planilha modelo do Dominio - cabecalho na linha %d:" % ih)
        for campo, col in sorted(mapa.items(), key=lambda x: x[1]):
            print("    coluna %-28s <- %s" % (cab[col], campo))
        vazias = [c for n, c in enumerate(cab) if c and n not in usadas]
        if vazias:
            avisos.append("colunas do modelo NAO preenchidas (confira se alguma e obrigatoria): " + "; ".join(vazias))
        colunas = cab
        linhas = [[ws.cell(row=ih + 1 + n, column=c).value for c in range(1, len(cab) + 1)] for n in range(len(itens))]
    else:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Saldo do Estoque"
        colunas = [r for _, r in CAMPOS_DOMINIO]
        ws.append(colunas)
        linhas = []
        for i in itens:
            linhas.append([_valor_dominio(i, c) for c, _ in CAMPOS_DOMINIO])
            ws.append(linhas[-1])
        avisos.append("SEM PLANILHA MODELO: as colunas desta planilha sao genericas e podem nao bater com o leiaute "
                      "do Importador. Baixe o modelo no Dominio e gere de novo com --modelo-dominio.")
    cx = os.path.join(a.saida, base + "_dominio_saldo_estoque.xlsx")
    wb.save(cx)
    arquivos.append(cx)
    cc = os.path.join(a.saida, base + "_dominio_saldo_estoque.csv")
    with open(cc, "w", encoding="cp1252", errors="replace", newline="") as f:
        w = csv.writer(f, delimiter=";", lineterminator="\r\n")
        for l in linhas:  # sem cabecalho, como o Importador pede
            w.writerow([("" if v is None else fmt(Decimal(str(v))) if isinstance(v, float) else v) for v in l])
    arquivos.append(cc)
    return arquivos, avisos


def gerar_sped(a, itens, data, base):
    """Arquivo no leiaute da EFD ICMS/IPI so com cadastros (0190/0200) e Bloco H, para importar no Dominio."""
    if data.month == 12:
        ini = dt.date(data.year + 1, 2, 1)  # inventario de 31/12 vai na EFD de fevereiro
    else:
        ini = dt.date(data.year + (data.month + 1 > 12), (data.month % 12) + 1, 1)
    prox = dt.date(ini.year + (ini.month == 12), ini.month % 12 + 1, 1)
    fim = prox - dt.timedelta(days=1)
    ver = "%03d" % (ini.year - 2006)
    d = lambda x: x.strftime("%d%m%Y")
    n = lambda v, c: fmt(v, c)
    L = []
    add = lambda *c: L.append("|" + "|".join(str(x) for x in c) + "|")
    add("0000", ver, "0", d(ini), d(fim), a.empresa[:100], so_digitos(a.cnpj), "", a.uf.upper(), so_digitos(a.ie), a.cod_mun, "", "", "A", "1")
    add("0001", "0")
    for un in sorted({i["unidade"] for i in itens}):
        add("0190", un[:6], un)
    for i in itens:
        add("0200", i["codigo"][:60], i["descricao"].replace("|", " "), i["ean"], "", i["unidade"][:6], i["grupo"], i["ncm"], "", i["ncm"][:2], "", "", "")
    add("0990", len(L) + 1)
    h0 = len(L)
    add("H001", "0")
    add("H005", d(data), n(sum(i["valor_total"] for i in itens), 2), a.motivo)
    for i in itens:
        add("H010", i["codigo"][:60], i["unidade"][:6], n(i["quantidade"], 3), n(i["custo_unitario"], 6), n(i["valor_total"], 2), "0", "", "", "", n(i["valor_total"], 2))
    add("H990", len(L) - h0 + 1)
    cont = defaultdict(int)
    for l in L:
        cont[l[1:5]] += 1
    cont["9001"], cont["9990"], cont["9999"] = 1, 1, 1
    cont["9900"] = len(cont) + 1
    add("9001", "0")
    for reg in sorted(cont):
        add("9900", reg, cont[reg])
    add("9990", cont["9900"] + 3)
    add("9999", len(L) + 1)
    caminho = os.path.join(a.saida, base + "_sped_bloco_h.txt")
    with open(caminho, "w", encoding="latin-1", errors="replace", newline="") as f:
        f.write("\r\n".join(L) + "\r\n")
    return caminho


def gerar(a, itens, avisos):
    data = data_br(a.data)
    if not data:
        raise SystemExit("ERRO: --data invalida (use dd/mm/aaaa).")
    os.makedirs(a.saida, exist_ok=True)
    premissas = {}
    arq = a.premissas or (os.path.join(a.pasta_trabalho, "premissas.json") if a.pasta_trabalho else "")
    if arq and os.path.exists(arq):
        with open(arq, encoding="utf-8") as f:
            premissas = json.load(f)
    base = "%s_%s" % (a.codigo_empresa or so_digitos(a.cnpj), data.strftime("%Y%m%d"))
    formatos = {f.strip().lower() for f in a.formatos.split(",")}
    total = sum(i["valor_total"] for i in itens)
    print("GERACAO - %s | %d itens | total %s | data %s" % (a.empresa, len(itens), brl(total), data.strftime("%d/%m/%Y")))
    extras = []
    if "excel" in formatos:
        print("  Excel  : " + gerar_excel(a, itens, data, base, premissas, avisos))
    if "livro" in formatos:
        print("  Livro  : " + gerar_livro(a, itens, data, base))
    if "dominio" in formatos:
        arqs, extras = gerar_dominio(a, itens, data, base)
        for x in arqs:
            print("  Dominio: " + x)
    if "sped" in formatos:
        print("  SPED   : " + gerar_sped(a, itens, data, base))
    for av in extras:
        print("  ATENCAO: " + av)
    if avisos:
        print("  %d aviso(s) de conferencia (NCM/unidade) - estao na aba Resumo do Excel." % len(avisos))
