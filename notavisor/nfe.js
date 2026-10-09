// Leitura de XML de NF-e / NFC-e / CT-e e utilitários da chave de acesso.
(function () {
  // ---------- XML ----------
  const kids = (el, name) => (el ? Array.from(el.children).filter(c => c.localName === name) : []);
  const child = (el, name) => kids(el, name)[0] || null;
  function path(el, p) {
    for (const n of p.split('/')) {
      if (!el) return null;
      el = child(el, n);
    }
    return el;
  }
  const txt = (el, p) => {
    const n = p ? path(el, p) : el;
    return n ? n.textContent.trim() : '';
  };
  const find = (el, name) => (el ? el.getElementsByTagNameNS('*', name)[0] || null : null);
  const findTxt = (el, name) => {
    const n = find(el, name);
    return n ? n.textContent.trim() : '';
  };

  // ---------- Tabelas ----------
  const UF = {
    11: 'RO', 12: 'AC', 13: 'AM', 14: 'RR', 15: 'PA', 16: 'AP', 17: 'TO', 21: 'MA', 22: 'PI', 23: 'CE',
    24: 'RN', 25: 'PB', 26: 'PE', 27: 'AL', 28: 'SE', 29: 'BA', 31: 'MG', 32: 'ES', 33: 'RJ', 35: 'SP',
    41: 'PR', 42: 'SC', 43: 'RS', 50: 'MS', 51: 'MT', 52: 'GO', 53: 'DF',
  };
  const MODELO = {
    55: 'NF-e', 65: 'NFC-e', 57: 'CT-e', 67: 'CT-e OS', 58: 'MDF-e', 59: 'CF-e SAT', 62: 'NFCom', 66: 'NF3e',
  };
  const TP_EMIS = {
    1: 'Normal', 2: 'Contingência FS-IA', 3: 'Contingência SCAN', 4: 'Contingência EPEC',
    5: 'Contingência FS-DA', 6: 'Contingência SVC-AN', 7: 'Contingência SVC-RS', 9: 'Contingência off-line NFC-e',
  };
  const MOD_FRETE = {
    0: '0 - Por conta do Remet. (CIF)', 1: '1 - Por conta do Dest. (FOB)', 2: '2 - Por conta de Terceiros',
    3: '3 - Próprio por conta do Remet.', 4: '4 - Próprio por conta do Dest.', 9: '9 - Sem Ocorrência de Transporte',
  };
  const T_PAG = {
    '01': 'Dinheiro', '02': 'Cheque', '03': 'Cartão de Crédito', '04': 'Cartão de Débito', '05': 'Crédito Loja',
    '10': 'Vale Alimentação', '11': 'Vale Refeição', '12': 'Vale Presente', '13': 'Vale Combustível',
    '15': 'Boleto Bancário', '16': 'Depósito Bancário', '17': 'PIX', '18': 'Transferência / Carteira Digital',
    '19': 'Fidelidade / Cashback', '20': 'PIX Estático', '21': 'Crédito em Loja',
    '22': 'Pagamento Eletrônico', '90': 'Sem Pagamento', '99': 'Outros',
  };

  // ---------- Chave de acesso ----------
  // Aceita CNPJ alfanumérico (valores = código ASCII − 48), conforme a regra vigente desde 2026.
  function dvChave(base43) {
    let soma = 0, peso = 2;
    for (let i = base43.length - 1; i >= 0; i--) {
      soma += (base43.charCodeAt(i) - 48) * peso;
      peso = peso === 9 ? 2 : peso + 1;
    }
    const resto = soma % 11;
    return resto < 2 ? 0 : 11 - resto;
  }

  function limparChave(s) {
    return String(s || '').toUpperCase().replace(/[^0-9A-Z]/g, '');
  }

  function analisarChave(entrada) {
    const c = limparChave(entrada);
    const erros = [];
    if (c.length !== 44) erros.push(`A chave deve ter 44 caracteres (informados: ${c.length}).`);
    else if (!/^\d{6}[0-9A-Z]{14}\d{24}$/.test(c)) erros.push('Formato inválido: só o CNPJ (posições 7 a 20) pode ter letras.');
    if (erros.length) return { chave: c, valida: false, erros };

    const dv = dvChave(c.slice(0, 43));
    const info = {
      chave: c,
      cUF: c.slice(0, 2),
      uf: UF[+c.slice(0, 2)] || '?',
      aamm: c.slice(2, 6),
      emissao: `${c.slice(4, 6)}/20${c.slice(2, 4)}`,
      cnpj: c.slice(6, 20),
      mod: c.slice(20, 22),
      modelo: MODELO[+c.slice(20, 22)] || 'Modelo ' + c.slice(20, 22),
      serie: String(+c.slice(22, 25)),
      numero: String(+c.slice(25, 34)),
      tpEmis: c.slice(34, 35),
      tipoEmissao: TP_EMIS[+c.slice(34, 35)] || c.slice(34, 35),
      cNF: c.slice(35, 43),
      dv: c.slice(43),
      dvCalculado: String(dv),
    };
    if (!UF[+info.cUF]) erros.push(`Código de UF desconhecido: ${info.cUF}.`);
    const mes = +c.slice(4, 6);
    if (mes < 1 || mes > 12) erros.push(`Mês de emissão inválido: ${c.slice(4, 6)}.`);
    if (info.dv !== info.dvCalculado) erros.push(`Dígito verificador não confere (informado ${info.dv}, esperado ${dv}).`);
    return Object.assign(info, { valida: erros.length === 0, erros });
  }

  // ---------- Parsers ----------
  function endereco(el) {
    if (!el) return {};
    return {
      lgr: txt(el, 'xLgr'), nro: txt(el, 'nro'), cpl: txt(el, 'xCpl'), bairro: txt(el, 'xBairro'),
      mun: txt(el, 'xMun'), uf: txt(el, 'UF'), cep: txt(el, 'CEP'), fone: txt(el, 'fone'),
    };
  }

  function pessoa(el, enderTag) {
    if (!el) return null;
    return {
      doc: txt(el, 'CNPJ') || txt(el, 'CPF') || txt(el, 'idEstrangeiro'),
      nome: txt(el, 'xNome'), fant: txt(el, 'xFant'), ie: txt(el, 'IE'), iest: txt(el, 'IEST'),
      im: txt(el, 'IM'), email: txt(el, 'email'), end: endereco(child(el, enderTag)),
    };
  }

  function protocolo(doc) {
    const p = find(doc, 'infProt');
    if (!p) return null;
    return { nProt: txt(p, 'nProt'), dh: txt(p, 'dhRecbto'), cStat: txt(p, 'cStat'), motivo: txt(p, 'xMotivo') };
  }

  function cancelada(doc) {
    // Eventos de cancelamento (110111) às vezes vêm no mesmo arquivo.
    return Array.from(doc.getElementsByTagNameNS('*', 'tpEvento')).some(e => e.textContent.trim() === '110111');
  }

  function parseNFe(doc, inf) {
    const ide = child(inf, 'ide');
    const tot = path(inf, 'total/ICMSTot');
    const ibs = find(child(inf, 'total'), 'IBSCBSTot');
    const transp = child(inf, 'transp');
    const transporta = child(transp, 'transporta');
    const veic = child(transp, 'veicTransp');
    const vol = kids(transp, 'vol');
    const sumVol = (tag, dec) => {
      const vals = vol.map(v => txt(v, tag)).filter(Boolean);
      if (!vals.length) return '';
      return dec ? vals.reduce((a, b) => a + parseFloat(b), 0) : vals.join(', ');
    };
    const cobr = child(inf, 'cobr');
    const pag = child(inf, 'pag');
    const infAdic = child(inf, 'infAdic');

    const itens = kids(inf, 'det').map(det => {
      const prod = child(det, 'prod');
      const imp = child(det, 'imposto');
      const icmsGrp = child(imp, 'ICMS');
      const icms = icmsGrp && icmsGrp.firstElementChild;
      const ipi = find(imp, 'IPITrib');
      const orig = txt(icms, 'orig');
      return {
        n: det.getAttribute('nItem'),
        cod: txt(prod, 'cProd'), desc: txt(prod, 'xProd'), ncm: txt(prod, 'NCM'), cfop: txt(prod, 'CFOP'),
        un: txt(prod, 'uCom'), qtd: txt(prod, 'qCom'), vUn: txt(prod, 'vUnCom'), vProd: txt(prod, 'vProd'),
        vDesc: txt(prod, 'vDesc'), ean: txt(prod, 'cEAN'),
        cst: orig + (txt(icms, 'CST') || txt(icms, 'CSOSN')),
        vBC: txt(icms, 'vBC'), pICMS: txt(icms, 'pICMS'), vICMS: txt(icms, 'vICMS'),
        vIPI: txt(ipi, 'vIPI'), pIPI: txt(ipi, 'pIPI'),
        infAd: txt(det, 'infAdProd'),
      };
    });

    const t = n => txt(tot, n);
    return {
      tipo: txt(ide, 'mod') === '65' ? 'nfce' : 'nfe',
      chave: (inf.getAttribute('Id') || '').replace(/^NFe/, ''),
      versao: inf.getAttribute('versao') || '',
      ide: {
        natOp: txt(ide, 'natOp'), mod: txt(ide, 'mod'), serie: txt(ide, 'serie'), nNF: txt(ide, 'nNF'),
        dhEmi: txt(ide, 'dhEmi') || txt(ide, 'dEmi'), dhSaiEnt: txt(ide, 'dhSaiEnt') || txt(ide, 'dSaiEnt'),
        hSaiEnt: txt(ide, 'hSaiEnt'), tpNF: txt(ide, 'tpNF'), tpEmis: txt(ide, 'tpEmis'), tpAmb: txt(ide, 'tpAmb'),
        dhCont: txt(ide, 'dhCont'), xJust: txt(ide, 'xJust'),
      },
      emit: pessoa(child(inf, 'emit'), 'enderEmit'),
      dest: pessoa(child(inf, 'dest'), 'enderDest'),
      itens,
      tot: {
        vBC: t('vBC'), vICMS: t('vICMS'), vBCST: t('vBCST'), vST: t('vST'), vII: t('vII'),
        vICMSUFRemet: t('vICMSUFRemet'), vICMSUFDest: t('vICMSUFDest'), vFCP: t('vFCP'), vFCPST: t('vFCPST'),
        vPIS: t('vPIS'), vCOFINS: t('vCOFINS'), vProd: t('vProd'), vFrete: t('vFrete'), vSeg: t('vSeg'),
        vDesc: t('vDesc'), vOutro: t('vOutro'), vIPI: t('vIPI'), vTotTrib: t('vTotTrib'), vNF: t('vNF'),
        vIBS: findTxt(ibs, 'vIBS'), vCBS: findTxt(ibs, 'vCBS'),
      },
      transp: {
        modFrete: txt(transp, 'modFrete'),
        doc: txt(transporta, 'CNPJ') || txt(transporta, 'CPF'), nome: txt(transporta, 'xNome'),
        ie: txt(transporta, 'IE'), ender: txt(transporta, 'xEnder'), mun: txt(transporta, 'xMun'),
        uf: txt(transporta, 'UF'), placa: txt(veic, 'placa'), placaUF: txt(veic, 'UF'), rntc: txt(veic, 'RNTC'),
        qVol: sumVol('qVol', true), esp: sumVol('esp'), marca: sumVol('marca'), nVol: sumVol('nVol'),
        pesoB: sumVol('pesoB', true), pesoL: sumVol('pesoL', true),
      },
      fat: cobr && child(cobr, 'fat') ? {
        nFat: txt(cobr, 'fat/nFat'), vOrig: txt(cobr, 'fat/vOrig'), vDesc: txt(cobr, 'fat/vDesc'), vLiq: txt(cobr, 'fat/vLiq'),
      } : null,
      dups: kids(cobr, 'dup').map(d => ({ n: txt(d, 'nDup'), venc: txt(d, 'dVenc'), v: txt(d, 'vDup') })),
      pag: kids(pag, 'detPag').map(d => ({ tPag: txt(d, 'tPag'), forma: T_PAG[txt(d, 'tPag')] || txt(d, 'xPag') || 'Outros', v: txt(d, 'vPag') })),
      troco: txt(pag, 'vTroco'),
      infCpl: txt(infAdic, 'infCpl'),
      infFisco: txt(infAdic, 'infAdFisco'),
      qrCode: findTxt(doc, 'qrCode'),
      urlChave: findTxt(doc, 'urlChave'),
      prot: protocolo(doc),
      cancelada: cancelada(doc),
    };
  }

  function parseCTe(doc, inf) {
    const ide = child(inf, 'ide');
    const vPrest = child(inf, 'vPrest');
    const infCarga = find(inf, 'infCarga');
    return {
      tipo: 'cte',
      chave: (inf.getAttribute('Id') || '').replace(/^CTe/, ''),
      ide: {
        natOp: txt(ide, 'natOp'), mod: txt(ide, 'mod'), serie: txt(ide, 'serie'), nCT: txt(ide, 'nCT'),
        dhEmi: txt(ide, 'dhEmi'), cfop: txt(ide, 'CFOP'), tpAmb: txt(ide, 'tpAmb'),
        origem: `${txt(ide, 'xMunIni')} / ${txt(ide, 'UFIni')}`, destino: `${txt(ide, 'xMunFim')} / ${txt(ide, 'UFFim')}`,
      },
      emit: pessoa(child(inf, 'emit'), 'enderEmit'),
      rem: pessoa(child(inf, 'rem'), 'enderReme'),
      dest: pessoa(child(inf, 'dest'), 'enderDest'),
      exped: pessoa(child(inf, 'exped'), 'enderExped'),
      receb: pessoa(child(inf, 'receb'), 'enderReceb'),
      vTPrest: txt(vPrest, 'vTPrest'), vRec: txt(vPrest, 'vRec'),
      comps: kids(vPrest, 'Comp').map(c => ({ nome: txt(c, 'xNome'), v: txt(c, 'vComp') })),
      carga: { vCarga: txt(infCarga, 'vCarga'), proPred: txt(infCarga, 'proPred') },
      docs: Array.from(inf.getElementsByTagNameNS('*', 'infNFe')).map(n => txt(n, 'chave')).filter(Boolean),
      obs: findTxt(inf, 'xObs'),
      prot: protocolo(doc),
      cancelada: cancelada(doc),
    };
  }

  function parse(texto) {
    const limpo = String(texto).replace(/^﻿/, '').trim();
    const doc = new DOMParser().parseFromString(limpo, 'application/xml');
    if (doc.getElementsByTagName('parsererror').length) throw new Error('O arquivo não é um XML válido.');
    const infNFe = find(doc, 'infNFe');
    if (infNFe && find(doc, 'ide')) {
      const cte = find(doc, 'infCte');
      if (cte) return parseCTe(doc, cte);
      return parseNFe(doc, infNFe);
    }
    const infCte = find(doc, 'infCte');
    if (infCte) return parseCTe(doc, infCte);
    if (find(doc, 'resNFe') || find(doc, 'procEventoNFe')) {
      throw new Error('Este XML é um resumo ou evento, não a nota completa.');
    }
    throw new Error('XML não reconhecido: esperado NF-e, NFC-e ou CT-e.');
  }

  window.NFe = { parse, analisarChave, dvChave, limparChave, UF, MODELO, MOD_FRETE, T_PAG };
})();
