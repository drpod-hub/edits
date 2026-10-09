// Monta o DANFE (NF-e), o DANFE NFC-e e um resumo do CT-e em HTML imprimível.
(function () {
  // ---------- Formatação ----------
  const esc = s => String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  const num = (v, d = 2) => (v === '' || v == null || isNaN(v) ? '' :
    Number(v).toLocaleString('pt-BR', { minimumFractionDigits: d, maximumFractionDigits: d }));
  const money = v => num(v || 0, 2);
  // Mantém as casas decimais significativas (quantidade/valor unitário), com no mínimo `min`.
  function numFlex(v, min = 2) {
    if (v === '' || v == null) return '';
    const dec = (String(v).split('.')[1] || '').replace(/0+$/, '').length;
    return num(v, Math.max(min, dec));
  }
  function fmtDoc(s) {
    s = String(s || '');
    if (s.length === 14) return s.replace(/^(.{2})(.{3})(.{3})(.{4})(.{2})$/, '$1.$2.$3/$4-$5');
    if (s.length === 11) return s.replace(/^(\d{3})(\d{3})(\d{3})(\d{2})$/, '$1.$2.$3-$4');
    return s;
  }
  const fmtCEP = s => (/^\d{8}$/.test(s || '') ? s.replace(/^(\d{5})(\d{3})$/, '$1-$2') : s || '');
  function fmtFone(s) {
    s = String(s || '').replace(/\D/g, '');
    if (s.length === 11) return s.replace(/^(\d{2})(\d{5})(\d{4})$/, '($1) $2-$3');
    if (s.length === 10) return s.replace(/^(\d{2})(\d{4})(\d{4})$/, '($1) $2-$3');
    return s;
  }
  const fmtData = s => (/^\d{4}-\d{2}-\d{2}/.test(s || '') ? `${s.slice(8, 10)}/${s.slice(5, 7)}/${s.slice(0, 4)}` : '');
  const fmtHora = s => ((s || '').length >= 19 ? s.slice(11, 19) : '');
  const fmtChave = c => String(c || '').replace(/(.{4})(?=.)/g, '$1 ');
  const fmtNum = n => String(n || '').padStart(9, '0').replace(/^(\d{3})(\d{3})(\d{3})$/, '$1.$2.$3');
  const linhaEnd = e => [e.lgr, e.nro, e.cpl].filter(Boolean).join(', ');

  // ---------- Peças do layout ----------
  const field = (label, value, cls = '') =>
    `<div class="f ${cls}"><span class="l">${esc(label)}</span><span class="v">${value === '' || value == null ? '&nbsp;' : esc(value)}</span></div>`;
  const row = (...cells) => `<div class="r">${cells.join('')}</div>`;
  const sec = t => `<div class="sec">${esc(t)}</div>`;

  function marcaDagua(n) {
    if (n.cancelada) return 'NF-e CANCELADA';
    if (n.ide.tpAmb === '2') return 'SEM VALOR FISCAL';
    if (!n.prot) return 'SEM PROTOCOLO DE AUTORIZAÇÃO';
    if (!['100', '150'].includes(n.prot.cStat)) return n.prot.cStat === '110' || n.prot.cStat === '301' || n.prot.cStat === '302' ? 'USO DENEGADO' : 'NÃO AUTORIZADA';
    return '';
  }

  function avisoAmbiente(n) {
    if (n.ide.tpAmb === '2') return '<div class="aviso">EMITIDA EM AMBIENTE DE HOMOLOGAÇÃO — SEM VALOR FISCAL</div>';
    if (!n.prot) return '<div class="aviso">XML sem protocolo de autorização: confira se a nota foi autorizada pela SEFAZ.</div>';
    return '';
  }

  // ---------- DANFE NF-e (retrato) ----------
  function danfeNFe(n) {
    const e = n.emit, d = n.dest || { end: {} }, t = n.tot, tr = n.transp;
    const prot = n.prot ? `${n.prot.nProt} - ${fmtData(n.prot.dh)} ${fmtHora(n.prot.dh)}` : '';
    const contingencia = n.ide.tpEmis && n.ide.tpEmis !== '1';
    const wm = marcaDagua(n);

    const canhoto = `
      <div class="canhoto">
        <div class="r">
          <div class="f grow"><span class="v small">RECEBEMOS DE ${esc(e.nome)} OS PRODUTOS E/OU SERVIÇOS CONSTANTES DA NOTA FISCAL ELETRÔNICA INDICADA AO LADO. EMISSÃO: ${fmtData(n.ide.dhEmi)} — DESTINATÁRIO: ${esc(d.nome)} — VALOR TOTAL: R$ ${money(t.vNF)}</span></div>
          <div class="f nfbox" style="width:30mm"><span class="v center"><b>NF-e</b><br>Nº ${fmtNum(n.ide.nNF)}<br>Série ${esc(n.ide.serie)}</span></div>
        </div>
        <div class="r">
          ${field('Data de recebimento', '', 'w35')}
          ${field('Identificação e assinatura do recebedor', '', 'grow')}
        </div>
      </div>
      <div class="corte"></div>`;

    const cab = `
      <div class="r cab">
        <div class="f emitente">
          <span class="l">Identificação do emitente</span>
          <div class="emit-nome">${esc(e.nome)}</div>
          <div class="emit-end">${esc(linhaEnd(e.end))}<br>${esc(e.end.bairro)} — ${esc(fmtCEP(e.end.cep))}<br>${esc(e.end.mun)} - ${esc(e.end.uf)}${e.end.fone ? ' — Fone: ' + esc(fmtFone(e.end.fone)) : ''}</div>
        </div>
        <div class="f danfe-id">
          <div class="danfe-t">DANFE</div>
          <div class="small center">Documento Auxiliar da<br>Nota Fiscal Eletrônica</div>
          <div class="es"><span class="small">0 - ENTRADA<br>1 - SAÍDA</span><span class="tp">${esc(n.ide.tpNF)}</span></div>
          <div class="center"><b>Nº ${fmtNum(n.ide.nNF)}</b><br><b>SÉRIE ${esc(n.ide.serie)}</b></div>
        </div>
        <div class="f chave-box">
          <div class="bc">${window.Code128.svg(n.chave)}</div>
          <span class="l">Chave de acesso</span>
          <span class="v mono center">${esc(fmtChave(n.chave))}</span>
          <div class="small center consulta">Consulta de autenticidade no portal nacional da NF-e<br>www.nfe.fazenda.gov.br/portal ou no site da Sefaz Autorizadora</div>
        </div>
      </div>
      ${row(field('Natureza da operação', n.ide.natOp, 'grow'),
        field(contingencia ? 'Emissão em contingência' : 'Protocolo de autorização de uso', contingencia && !prot ? (n.ide.xJust || 'Contingência') : prot, 'w80 center'))}
      ${row(field('Inscrição estadual', e.ie, 'grow'), field('Insc. estadual do subst. tributário', e.iest, 'grow'), field('CNPJ / CPF', fmtDoc(e.doc), 'grow'))}`;

    const dest = `
      ${sec('Destinatário / Remetente')}
      ${row(field('Nome / Razão social', d.nome, 'grow'), field('CNPJ / CPF', fmtDoc(d.doc), 'w40'), field('Data da emissão', fmtData(n.ide.dhEmi), 'w25 center'))}
      ${row(field('Endereço', linhaEnd(d.end), 'grow'), field('Bairro / Distrito', d.end.bairro, 'w40'), field('CEP', fmtCEP(d.end.cep), 'w20 center'), field('Data da saída/entrada', fmtData(n.ide.dhSaiEnt), 'w25 center'))}
      ${row(field('Município', d.end.mun, 'grow'), field('Fone / Fax', fmtFone(d.end.fone), 'w30'), field('UF', d.end.uf, 'w10 center'), field('Inscrição estadual', d.ie, 'w30'), field('Hora da saída/entrada', fmtHora(n.ide.dhSaiEnt) || n.ide.hSaiEnt, 'w25 center'))}`;

    let fatura = '';
    if (n.dups.length || n.fat) {
      const dups = n.dups.map(x => `<div class="dup"><span>${esc(x.n)}</span><span>${fmtData(x.venc)}</span><span>R$ ${money(x.v)}</span></div>`).join('');
      const fat = n.fat && !n.dups.length
        ? `<div class="small">Fatura ${esc(n.fat.nFat)} — Valor original R$ ${money(n.fat.vOrig)} — Desconto R$ ${money(n.fat.vDesc)} — Valor líquido R$ ${money(n.fat.vLiq)}</div>` : '';
      fatura = `${sec('Fatura / Duplicatas')}<div class="f dups">${dups}${fat}</div>`;
    }

    const imposto = `
      ${sec('Cálculo do imposto')}
      ${row(field('Base de cálc. do ICMS', money(t.vBC), 'grow num'), field('Valor do ICMS', money(t.vICMS), 'grow num'),
        field('Base de cálc. ICMS S.T.', money(t.vBCST), 'grow num'), field('Valor do ICMS subst.', money(t.vST), 'grow num'),
        field('V. imp. importação', money(t.vII), 'grow num'), field('V. ICMS UF remet.', money(t.vICMSUFRemet), 'grow num'),
        field('Valor do FCP', money(t.vFCP), 'grow num'), field('Valor do PIS', money(t.vPIS), 'grow num'),
        field('V. total produtos', money(t.vProd), 'grow num'))}
      ${row(field('Valor do frete', money(t.vFrete), 'grow num'), field('Valor do seguro', money(t.vSeg), 'grow num'),
        field('Desconto', money(t.vDesc), 'grow num'), field('Outras despesas', money(t.vOutro), 'grow num'),
        field('Valor total IPI', money(t.vIPI), 'grow num'), field('V. ICMS UF dest.', money(t.vICMSUFDest), 'grow num'),
        field('V. tot. tributos', money(t.vTotTrib), 'grow num'), field('Valor da COFINS', money(t.vCOFINS), 'grow num'),
        field('Valor total da nota', money(t.vNF), 'grow num strong'))}
      ${t.vIBS || t.vCBS ? row(field('Valor do IBS', money(t.vIBS), 'grow num'), field('Valor da CBS', money(t.vCBS), 'grow num'), '<div class="f grow3"></div>') : ''}`;

    const transp = `
      ${sec('Transportador / Volumes transportados')}
      ${row(field('Nome / Razão social', tr.nome, 'grow'), field('Frete por conta', window.NFe.MOD_FRETE[tr.modFrete] || tr.modFrete, 'w45'),
        field('Código ANTT', tr.rntc, 'w20'), field('Placa do veículo', tr.placa, 'w20'), field('UF', tr.placaUF, 'w10 center'), field('CNPJ / CPF', fmtDoc(tr.doc), 'w35'))}
      ${row(field('Endereço', tr.ender, 'grow'), field('Município', tr.mun, 'w45'), field('UF', tr.uf, 'w10 center'), field('Inscrição estadual', tr.ie, 'w35'))}
      ${row(field('Quantidade', tr.qVol === '' ? '' : num(tr.qVol, 0), 'grow'), field('Espécie', tr.esp, 'grow'), field('Marca', tr.marca, 'grow'),
        field('Numeração', tr.nVol, 'grow'), field('Peso bruto', tr.pesoB === '' ? '' : num(tr.pesoB, 3), 'grow num'), field('Peso líquido', tr.pesoL === '' ? '' : num(tr.pesoL, 3), 'grow num'))}`;

    const linhas = n.itens.map(i => `
      <tr>
        <td>${esc(i.cod)}</td>
        <td class="desc">${esc(i.desc)}${i.infAd ? `<div class="infad">${esc(i.infAd)}</div>` : ''}</td>
        <td class="c">${esc(i.ncm)}</td><td class="c">${esc(i.cst)}</td><td class="c">${esc(i.cfop)}</td><td class="c">${esc(i.un)}</td>
        <td class="n">${numFlex(i.qtd, 2)}</td><td class="n">${numFlex(i.vUn, 2)}</td><td class="n">${money(i.vProd)}</td>
        <td class="n">${num(i.vBC)}</td><td class="n">${num(i.vICMS)}</td><td class="n">${num(i.vIPI)}</td>
        <td class="n">${num(i.pICMS)}</td><td class="n">${num(i.pIPI)}</td>
      </tr>`).join('');

    const produtos = `
      ${sec('Dados dos produtos / serviços')}
      <table class="itens">
        <thead><tr>
          <th>Código</th><th>Descrição do produto / serviço</th><th>NCM/SH</th><th>CST</th><th>CFOP</th><th>UN</th>
          <th>Quant.</th><th>Valor unit.</th><th>Valor total</th><th>B.cálc ICMS</th><th>Valor ICMS</th><th>Valor IPI</th><th>Alíq. ICMS</th><th>Alíq. IPI</th>
        </tr></thead>
        <tbody>${linhas}</tbody>
      </table>`;

    const adic = [
      n.infFisco && 'Inf. fisco: ' + n.infFisco,
      n.infCpl,
      contingencia && `DANFE em contingência (${n.ide.dhCont ? fmtData(n.ide.dhCont) + ' ' + fmtHora(n.ide.dhCont) : 'tpEmis ' + n.ide.tpEmis}). ${n.ide.xJust || ''}`,
    ].filter(Boolean).map(esc).join('<br>');

    const dadosAdic = `
      ${sec('Dados adicionais')}
      <div class="r adic">
        <div class="f grow"><span class="l">Informações complementares</span><span class="v small pre">${adic || '&nbsp;'}</span></div>
        <div class="f w60"><span class="l">Reservado ao fisco</span><span class="v">&nbsp;</span></div>
      </div>`;

    return `
      <article class="danfe a4">
        ${wm ? `<div class="wm">${esc(wm)}</div>` : ''}
        ${avisoAmbiente(n)}
        ${canhoto}${cab}${dest}${fatura}${imposto}${transp}${produtos}${dadosAdic}
      </article>`;
  }

  // ---------- DANFE NFC-e (bobina 80 mm) ----------
  function danfeNFCe(n) {
    const e = n.emit, d = n.dest, t = n.tot;
    const wm = marcaDagua(n);
    const itens = n.itens.map(i => `
      <tr><td colspan="5" class="desc">${esc(i.cod)} ${esc(i.desc)}</td></tr>
      <tr><td></td><td class="n">${numFlex(i.qtd, 0)}</td><td>${esc(i.un)}</td><td class="n">x ${numFlex(i.vUn, 2)}</td><td class="n">${money(i.vProd)}</td></tr>`).join('');
    const pag = n.pag.map(p => `<div class="lin"><span>${esc(p.forma)}</span><span>${money(p.v)}</span></div>`).join('');
    const consumidor = d && d.doc
      ? `CONSUMIDOR — ${d.doc.length === 11 ? 'CPF' : 'CNPJ'} ${esc(fmtDoc(d.doc))}${d.nome ? '<br>' + esc(d.nome) : ''}`
      : 'CONSUMIDOR NÃO IDENTIFICADO';
    const prot = n.prot
      ? `Protocolo de autorização: ${esc(n.prot.nProt)}<br>Data de autorização: ${fmtData(n.prot.dh)} ${fmtHora(n.prot.dh)}` : '';

    return `
      <article class="danfe nfce">
        ${wm ? `<div class="wm">${esc(wm)}</div>` : ''}
        <div class="center">
          <b>${esc(e.nome)}</b><br>
          CNPJ: ${esc(fmtDoc(e.doc))} IE: ${esc(e.ie)}<br>
          ${esc(linhaEnd(e.end))}, ${esc(e.end.bairro)}, ${esc(e.end.mun)} - ${esc(e.end.uf)}
        </div>
        <hr>
        <div class="center"><b>DANFE NFC-e — Documento Auxiliar da Nota Fiscal de Consumidor Eletrônica</b></div>
        ${n.ide.tpAmb === '2' ? '<div class="center"><b>EMITIDA EM AMBIENTE DE HOMOLOGAÇÃO — SEM VALOR FISCAL</b></div>' : ''}
        ${n.ide.tpEmis === '9' ? '<div class="center"><b>EMITIDA EM CONTINGÊNCIA</b><br>Pendente de autorização</div>' : ''}
        <hr>
        <table class="itens-nfce">
          <thead><tr><th colspan="5" class="desc">Código Descrição</th></tr><tr><th></th><th class="n">Qtde</th><th>UN</th><th class="n">Vl unit.</th><th class="n">Vl total</th></tr></thead>
          <tbody>${itens}</tbody>
        </table>
        <hr>
        <div class="lin"><span>Qtd. total de itens</span><span>${n.itens.length}</span></div>
        <div class="lin"><span>Valor total R$</span><span>${money(t.vProd)}</span></div>
        ${+t.vDesc ? `<div class="lin"><span>Descontos R$</span><span>${money(t.vDesc)}</span></div>` : ''}
        ${+t.vFrete ? `<div class="lin"><span>Frete R$</span><span>${money(t.vFrete)}</span></div>` : ''}
        ${+t.vOutro ? `<div class="lin"><span>Acréscimos R$</span><span>${money(t.vOutro)}</span></div>` : ''}
        <div class="lin big"><span>Valor a pagar R$</span><span>${money(t.vNF)}</span></div>
        <div class="lin"><span><b>Forma de pagamento</b></span><span><b>Valor pago R$</b></span></div>
        ${pag}
        ${+n.troco ? `<div class="lin"><span>Troco R$</span><span>${money(n.troco)}</span></div>` : ''}
        <hr>
        <div class="center">
          Consulte pela chave de acesso em<br><span class="break">${esc(n.urlChave || 'site da SEFAZ do seu estado')}</span><br>
          <span class="mono">${esc(fmtChave(n.chave))}</span>
        </div>
        <hr>
        <div class="center">${consumidor}</div>
        <hr>
        <div class="center">
          <b>NFC-e nº ${esc(n.ide.nNF)} Série ${esc(n.ide.serie)} ${fmtData(n.ide.dhEmi)} ${fmtHora(n.ide.dhEmi)}</b><br>${prot}
        </div>
        <div class="qr" data-qr="${esc(n.qrCode)}"></div>
        ${+t.vTotTrib ? `<div class="center small">Tributos totais incidentes (Lei Federal 12.741/2012): R$ ${money(t.vTotTrib)}</div>` : ''}
        ${n.infCpl ? `<hr><div class="small pre">${esc(n.infCpl)}</div>` : ''}
      </article>`;
  }

  // ---------- Resumo do CT-e ----------
  function resumoCTe(c) {
    const p = (titulo, x) => (x ? `${sec(titulo)}${row(field('Nome / Razão social', x.nome, 'grow'), field('CNPJ / CPF', fmtDoc(x.doc), 'w40'), field('IE', x.ie, 'w30'))}
      ${row(field('Endereço', [linhaEnd(x.end), x.end.bairro].filter(Boolean).join(' — '), 'grow'), field('Município / UF', `${x.end.mun || ''} - ${x.end.uf || ''}`, 'w50'))}` : '');
    const prot = c.prot ? `${c.prot.nProt} - ${fmtData(c.prot.dh)} ${fmtHora(c.prot.dh)}` : '';
    const wm = c.cancelada ? 'CT-e CANCELADO' : c.ide.tpAmb === '2' ? 'SEM VALOR FISCAL' : !c.prot ? 'SEM PROTOCOLO DE AUTORIZAÇÃO' : '';
    return `
      <article class="danfe a4">
        ${wm ? `<div class="wm">${esc(wm)}</div>` : ''}
        <div class="r cab">
          <div class="f emitente"><span class="l">Emitente</span><div class="emit-nome">${esc(c.emit.nome)}</div>
            <div class="emit-end">CNPJ ${esc(fmtDoc(c.emit.doc))} — IE ${esc(c.emit.ie)}<br>${esc(linhaEnd(c.emit.end))}<br>${esc(c.emit.end.mun)} - ${esc(c.emit.end.uf)}</div></div>
          <div class="f danfe-id"><div class="danfe-t">CT-e</div><div class="small center">Resumo do Conhecimento<br>de Transporte Eletrônico</div>
            <div class="center"><b>Nº ${esc(c.ide.nCT)}</b><br><b>SÉRIE ${esc(c.ide.serie)}</b></div></div>
          <div class="f chave-box"><div class="bc">${window.Code128.svg(c.chave)}</div><span class="l">Chave de acesso</span>
            <span class="v mono center">${esc(fmtChave(c.chave))}</span>
            <div class="small center consulta">Consulta em www.cte.fazenda.gov.br/portal</div></div>
        </div>
        ${row(field('CFOP - Natureza da operação', `${c.ide.cfop} - ${c.ide.natOp}`, 'grow'), field('Data de emissão', `${fmtData(c.ide.dhEmi)} ${fmtHora(c.ide.dhEmi)}`, 'w40'), field('Protocolo de autorização', prot, 'w60'))}
        ${row(field('Início da prestação', c.ide.origem, 'grow'), field('Término da prestação', c.ide.destino, 'grow'))}
        ${p('Remetente', c.rem)}${p('Destinatário', c.dest)}${p('Expedidor', c.exped)}${p('Recebedor', c.receb)}
        ${sec('Valores da prestação')}
        ${row(...c.comps.map(x => field(x.nome, money(x.v), 'grow num')), field('Valor total do serviço', money(c.vTPrest), 'grow num strong'), field('Valor a receber', money(c.vRec), 'grow num'))}
        ${sec('Carga')}
        ${row(field('Produto predominante', c.carga.proPred, 'grow'), field('Valor da carga', money(c.carga.vCarga), 'w40 num'))}
        ${c.docs.length ? sec('Documentos originários (NF-e)') + `<div class="f"><span class="v mono small">${c.docs.map(x => esc(fmtChave(x))).join('<br>')}</span></div>` : ''}
        ${c.obs ? sec('Observações') + `<div class="f"><span class="v small pre">${esc(c.obs)}</span></div>` : ''}
        <div class="aviso">Este é um resumo do CT-e para conferência; não substitui o DACTE oficial.</div>
      </article>`;
  }

  function render(n) {
    if (n.tipo === 'nfce') return danfeNFCe(n);
    if (n.tipo === 'cte') return resumoCTe(n);
    return danfeNFe(n);
  }

  window.Danfe = { render, fmt: { esc, money, num, fmtDoc, fmtData, fmtHora, fmtChave, fmtNum } };
})();
