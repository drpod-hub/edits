// Interface: abas, upload/arrastar, lista de notas, impressão e consulta de chave.
(function () {
  const $ = s => document.querySelector(s);
  const { esc, money, fmtDoc, fmtData, fmtChave } = window.Danfe.fmt;

  const PORTAL = {
    nfe: 'https://www.nfe.fazenda.gov.br/portal/consultaRecaptcha.aspx?tipoConsulta=resumo&tipoConteudo=7PhJ+gAVw2g=',
    cte: 'https://www.cte.fazenda.gov.br/portal/consultaRecaptcha.aspx?tipoConsulta=completa&tipoConteudo=mCK/KoCqru0=',
  };

  const notas = []; // { nome, xml, dados }
  let atual = -1;

  // ---------- Abas ----------
  document.querySelectorAll('.aba').forEach(b => b.addEventListener('click', () => {
    document.querySelectorAll('.aba').forEach(x => {
      x.classList.toggle('ativa', x === b);
      x.setAttribute('aria-selected', x === b);
    });
    $('#aba-xml').hidden = b.dataset.aba !== 'xml';
    $('#aba-chave').hidden = b.dataset.aba !== 'chave';
  }));

  // ---------- Entrada de arquivos ----------
  const drop = $('#drop');
  ['dragenter', 'dragover'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add('sobre'); }));
  ['dragleave', 'drop'].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove('sobre'); }));
  drop.addEventListener('drop', e => abrirArquivos(e.dataTransfer.files));
  drop.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); $('#arquivo').click(); } });
  $('#arquivo').addEventListener('change', e => { abrirArquivos(e.target.files); e.target.value = ''; });
  // Permite soltar o arquivo em qualquer lugar da página.
  window.addEventListener('dragover', e => e.preventDefault());
  window.addEventListener('drop', e => { e.preventDefault(); if (e.target.closest && !e.target.closest('#drop')) abrirArquivos(e.dataTransfer.files); });

  $('#btn-colar').addEventListener('click', () => {
    const t = $('#xml-texto').value.trim();
    if (!t) return;
    limparErros();
    adicionar('XML colado', t);
  });

  document.querySelectorAll('[data-exemplo]').forEach(a => a.addEventListener('click', e => {
    e.preventDefault();
    limparErros();
    const tipo = a.dataset.exemplo;
    adicionar(tipo === 'nfce' ? 'exemplo-nfce.xml' : 'exemplo-nfe.xml', window.EXEMPLOS[tipo]);
  }));

  async function abrirArquivos(lista) {
    limparErros();
    for (const f of Array.from(lista || [])) {
      if (!/\.xml$/i.test(f.name) && !/xml/.test(f.type)) { erro(`${f.name}: não é um arquivo XML.`); continue; }
      try { adicionar(f.name, await lerTexto(f)); } catch (err) { erro(`${f.name}: ${err.message}`); }
    }
  }

  // XML de NF-e é UTF-8, mas alguns sistemas antigos gravam em ISO-8859-1.
  async function lerTexto(f) {
    const buf = await f.arrayBuffer();
    const head = new TextDecoder('ascii').decode(buf.slice(0, 200));
    const enc = /encoding=["'](iso-8859-1|latin1|windows-1252)["']/i.test(head) ? 'windows-1252' : 'utf-8';
    return new TextDecoder(enc).decode(buf);
  }

  function adicionar(nome, xml) {
    let dados;
    try { dados = window.NFe.parse(xml); } catch (err) { erro(`${nome}: ${err.message}`); return; }
    const existente = notas.findIndex(n => n.dados.chave && n.dados.chave === dados.chave);
    if (existente >= 0) { mostrar(existente); return; }
    notas.push({ nome, xml, dados });
    mostrar(notas.length - 1);
  }

  // ---------- Lista e visualização ----------
  function desenharLista() {
    $('#notas').innerHTML = notas.map((n, i) => {
      const d = n.dados;
      const num = d.ide.nNF || d.ide.nCT;
      const tipo = d.tipo === 'nfce' ? 'NFC-e' : d.tipo === 'cte' ? 'CT-e' : 'NF-e';
      const valor = d.tipo === 'cte' ? d.vTPrest : d.tot.vNF;
      return `<li><button class="${i === atual ? 'sel' : ''}" data-i="${i}">
        <span class="t"><b>${tipo} ${esc(num)}</b><span>R$ ${money(valor)}</span></span>
        <span class="s">${esc(d.emit.nome)}</span>
        <span class="s">${fmtData(d.ide.dhEmi)}${d.ide.tpAmb === '2' ? ' · homologação' : ''}${d.cancelada ? ' · cancelada' : ''}</span>
      </button></li>`;
    }).join('');
    $('#notas').querySelectorAll('button').forEach(b => b.addEventListener('click', () => mostrar(+b.dataset.i)));
  }

  function mostrar(i) {
    atual = i;
    const n = notas[i], d = n.dados;
    $('#area').hidden = false;
    $('#doc').innerHTML = window.Danfe.render(d);
    $('#doc').className = d.tipo;
    desenharQR();
    desenharLista();
    $('#resumo').innerHTML = resumo(d);
    ajustarPagina(d);
    $('#btn-consultar').href = d.tipo === 'nfce' && d.urlChave ? d.urlChave : d.tipo === 'cte' ? PORTAL.cte : PORTAL.nfe;
    document.title = `${d.tipo === 'cte' ? 'CT-e' : 'DANFE'} ${d.ide.nNF || d.ide.nCT} — NotaVisor`;
    $('#area').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  // A4 para NF-e/CT-e; para NFC-e, papel de 80 mm com a altura do cupom.
  function ajustarPagina(d) {
    let regra = '@page { size: A4; margin: 6mm; }';
    if (d.tipo === 'nfce') {
      const el = document.querySelector('#doc .danfe');
      const mm = Math.ceil(el.getBoundingClientRect().height * 25.4 / 96) + 6;
      regra = `@page { size: 80mm ${mm}mm; margin: 2mm; }`;
    }
    $('#page-size').textContent = regra;
  }

  function resumo(d) {
    const chave = window.NFe.analisarChave(d.chave);
    const st = d.cancelada ? ['ruim', 'Cancelada']
      : !d.prot ? ['alerta', 'Sem protocolo de autorização']
      : ['100', '150'].includes(d.prot.cStat) ? ['bom', `Autorizada · protocolo ${d.prot.nProt}`]
      : ['ruim', `${d.prot.cStat} - ${d.prot.motivo}`];
    return `
      <span class="selo ${st[0]}">${esc(st[1])}</span>
      ${d.ide.tpAmb === '2' ? '<span class="selo alerta">Homologação (sem valor fiscal)</span>' : ''}
      ${chave.valida ? '' : `<span class="selo ruim">Chave inválida: ${esc(chave.erros[0])}</span>`}
      <span class="chave-txt mono">${esc(fmtChave(d.chave))}</span>`;
  }

  function desenharQR() {
    document.querySelectorAll('#doc .qr[data-qr]').forEach(el => {
      const data = el.dataset.qr;
      if (!data) return;
      if (typeof window.qrcode !== 'function') {
        el.innerHTML = `<div class="small break">QR Code: ${esc(data)}</div>`;
        return;
      }
      const qr = window.qrcode(0, 'M');
      qr.addData(data);
      qr.make();
      el.innerHTML = qr.createSvgTag({ cellSize: 3, margin: 2, scalable: true });
    });
  }

  $('#btn-imprimir').addEventListener('click', () => window.print());

  $('#btn-baixar').addEventListener('click', () => {
    const n = notas[atual];
    if (!n) return;
    const nome = n.dados.chave ? `${n.dados.chave}-${n.dados.tipo}.xml` : n.nome;
    const url = URL.createObjectURL(new Blob([n.xml], { type: 'application/xml' }));
    const a = Object.assign(document.createElement('a'), { href: url, download: nome });
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });

  $('#btn-copiar').addEventListener('click', () => copiar(notas[atual] && notas[atual].dados.chave, $('#btn-copiar')));
  // A consulta oficial pede a chave digitada: já deixamos copiada.
  $('#btn-consultar').addEventListener('click', () => copiar(notas[atual] && notas[atual].dados.chave));

  async function copiar(texto, botao) {
    if (!texto) return;
    try {
      await navigator.clipboard.writeText(texto);
      if (botao) {
        const orig = botao.textContent;
        botao.textContent = 'Chave copiada ✓';
        setTimeout(() => { botao.textContent = orig; }, 1600);
      }
    } catch (_) { /* sem permissão de área de transferência */ }
  }

  $('#btn-limpar').addEventListener('click', () => {
    notas.length = 0;
    atual = -1;
    $('#area').hidden = true;
    $('#doc').innerHTML = '';
    document.title = 'NotaVisor — DANFE a partir do XML';
  });

  // ---------- Erros ----------
  function erro(msg) {
    const box = $('#erros');
    box.hidden = false;
    box.insertAdjacentHTML('beforeend', `<div>${esc(msg)}</div>`);
  }
  function limparErros() { $('#erros').innerHTML = ''; $('#erros').hidden = true; }

  // ---------- Consulta de chave ----------
  const campo = $('#chave');
  campo.addEventListener('input', () => {
    const limpa = window.NFe.limparChave(campo.value).slice(0, 44);
    const fmt = fmtChave(limpa);
    if (fmt !== campo.value) campo.value = fmt;
  });
  campo.addEventListener('paste', () => setTimeout(() => $('#form-chave').requestSubmit(), 0));

  $('#form-chave').addEventListener('submit', e => {
    e.preventDefault();
    const r = window.NFe.analisarChave(campo.value);
    const out = $('#chave-res');
    if (!r.cUF) {
      out.innerHTML = `<div class="cartao"><span class="selo ruim">Chave inválida</span><ul>${r.erros.map(x => `<li>${esc(x)}</li>`).join('')}</ul></div>`;
      return;
    }
    const portal = ['57', '67'].includes(r.mod) ? PORTAL.cte : PORTAL.nfe;
    const linha = (k, v) => `<tr><th>${esc(k)}</th><td>${esc(v)}</td></tr>`;
    out.innerHTML = `
      <div class="cartao">
        ${r.valida ? '<span class="selo bom">Chave válida</span>' : `<span class="selo ruim">Chave com problema</span><ul>${r.erros.map(x => `<li>${esc(x)}</li>`).join('')}</ul>`}
        <div class="bc-grande">${window.Code128.svg(r.chave)}</div>
        <div class="mono center">${esc(fmtChave(r.chave))}</div>
        <table class="info">
          ${linha('Documento', `${r.modelo} (modelo ${r.mod})`)}
          ${linha('UF do emitente', `${r.uf} (${r.cUF})`)}
          ${linha('Emissão', r.emissao)}
          ${linha('CNPJ / CPF do emitente', fmtDoc(r.cnpj.replace(/^000(\d{11})$/, '$1')))}
          ${linha('Série', r.serie)}
          ${linha('Número', r.numero)}
          ${linha('Tipo de emissão', r.tipoEmissao)}
          ${linha('Código numérico', r.cNF)}
          ${linha('Dígito verificador', r.dv + (r.dv === r.dvCalculado ? ' ✓' : ` (esperado ${r.dvCalculado})`))}
        </table>
        ${r.valida && srv.ativo && r.mod === '55' ? `<p><button class="btn primario" id="btn-baixar-sefaz">Baixar XML com meu certificado</button></p><div id="baixar-msg"></div>` : ''}
        ${r.valida ? `<p><a class="btn${srv.ativo ? '' : ' primario'}" href="${portal}" target="_blank" rel="noopener" id="ir-portal">Consultar no portal oficial ↗</a>
          <span class="small">A chave já fica copiada: basta colar no campo do portal.</span></p>` : ''}
      </div>`;
    const ir = $('#ir-portal');
    if (ir) ir.addEventListener('click', () => copiar(r.chave));
    const bx = $('#btn-baixar-sefaz');
    if (bx) bx.addEventListener('click', () => baixarDaSefaz(r.chave, bx));
  });

  // ---------- Servidor com certificado (opcional) ----------
  // Quando o site é aberto pelo servidor/servidor.js, dá para baixar o XML direto da SEFAZ.
  const srv = { ativo: false };

  async function api(caminho, opcoes = {}) {
    const headers = Object.assign({ 'Content-Type': 'application/json' }, opcoes.headers || {});
    const token = lerToken();
    if (token) headers.Authorization = 'Bearer ' + token;
    const r = await fetch(caminho, Object.assign({}, opcoes, { headers }));
    if (r.status === 401) {
      const novo = prompt('Token de acesso do servidor NotaVisor:');
      if (novo) { gravarToken(novo); return api(caminho, opcoes); }
    }
    const tipo = r.headers.get('content-type') || '';
    return { status: r.status, dados: tipo.includes('json') ? await r.json() : await r.text() };
  }
  function lerToken() { try { return localStorage.getItem('notavisor-token') || ''; } catch (_) { return ''; } }
  function gravarToken(t) { try { localStorage.setItem('notavisor-token', t); } catch (_) { /* sem storage */ } }

  async function iniciarServidor() {
    if (location.protocol === 'file:') return;
    let st;
    try {
      const r = await fetch('api/status');
      if (!r.ok) return;
      st = await r.json();
    } catch (_) { return; } // site estático, sem servidor
    $('#srv').hidden = false;
    if (!st.ativo) {
      $('#srv-info').textContent = 'Servidor sem certificado configurado: ' + st.erro;
      $('#btn-sincronizar').hidden = true;
      return;
    }
    srv.ativo = true;
    const venc = st.validade ? new Date(st.validade).toLocaleDateString('pt-BR') : '';
    $('#srv-info').textContent = `${st.titular} · ${fmtDoc(st.doc)} · certificado válido até ${venc} · ${st.ambiente}`;
    listarNotasServidor();
  }

  function msgServidor(el, tipo, texto) {
    el.hidden = false;
    el.innerHTML = `<span class="selo ${tipo}">${tipo === 'bom' ? 'Pronto' : tipo === 'alerta' ? 'Atenção' : 'Erro'}</span> ${esc(texto)}`;
  }

  async function baixarDaSefaz(chave, botao) {
    const out = $('#baixar-msg');
    botao.disabled = true;
    const orig = botao.textContent;
    botao.textContent = 'Consultando a SEFAZ…';
    try {
      const { status, dados } = await api('api/baixar', { method: 'POST', body: JSON.stringify({ chave }) });
      if (status === 200 && dados.xml) {
        msgServidor(out, 'bom', dados.origem === 'cache' ? 'XML já estava salvo no servidor.' : 'XML baixado da SEFAZ.');
        abrirNoVisor(chave + '.xml', dados.xml);
        listarNotasServidor();
      } else if (dados.resumo) {
        const x = dados.resumo;
        msgServidor(out, 'alerta', `${dados.mensagem || ''} Resumo: ${x.emitente} · R$ ${money(x.valor)} · ${fmtData(x.emissao)} · ${x.situacao}`);
        listarNotasServidor();
      } else {
        msgServidor(out, status === 429 ? 'alerta' : 'ruim', dados.mensagem || dados.erro || 'Falha desconhecida.');
      }
    } catch (err) {
      msgServidor(out, 'ruim', 'Não foi possível falar com o servidor: ' + err.message);
    } finally {
      botao.disabled = false;
      botao.textContent = orig;
    }
  }

  $('#btn-sincronizar').addEventListener('click', async () => {
    const b = $('#btn-sincronizar'), out = $('#srv-msg');
    b.disabled = true;
    b.textContent = 'Buscando…';
    try {
      const { status, dados } = await api('api/sincronizar', { method: 'POST' });
      if (status === 200) {
        const partes = [`${dados.novas.length} nota(s) completa(s) baixada(s)`];
        if (dados.resumos.length) partes.push(`${dados.resumos.length} resumo(s)`);
        if (dados.ciencias) partes.push(`ciência registrada em ${dados.ciencias}: os XMLs chegam na próxima busca`);
        if (dados.proxima) partes.push('próxima busca liberada às ' + new Date(dados.proxima).toLocaleTimeString('pt-BR'));
        msgServidor(out, 'bom', partes.join(' · ') + '.');
      } else {
        msgServidor(out, status === 429 ? 'alerta' : 'ruim', dados.mensagem || dados.erro);
      }
      listarNotasServidor();
    } catch (err) {
      msgServidor(out, 'ruim', err.message);
    } finally {
      b.disabled = false;
      b.textContent = 'Buscar notas novas';
    }
  });

  async function listarNotasServidor() {
    const { status, dados } = await api('api/notas');
    if (status !== 200) return;
    const ul = $('#srv-notas');
    ul.innerHTML = dados.notas.length ? dados.notas.map(n => `
      <li>
        <div><b>NF-e ${esc(n.numero)}</b> · ${esc(n.emitente)}<div class="small muted">${fmtData(n.emissao)} · R$ ${money(n.valor)}${n.completa ? '' : ' · só resumo (aguardando XML)'}</div></div>
        ${n.completa ? `<button class="btn" data-chave="${esc(n.chave)}">Abrir</button>` : ''}
      </li>`).join('') : '<li class="muted small">Nenhuma nota baixada ainda.</li>';
    ul.querySelectorAll('[data-chave]').forEach(b => b.addEventListener('click', async () => {
      const r = await api('api/notas/' + b.dataset.chave);
      if (r.status === 200) abrirNoVisor(b.dataset.chave + '.xml', r.dados);
    }));
  }

  function abrirNoVisor(nome, xml) {
    document.querySelector('.aba[data-aba="xml"]').click();
    limparErros();
    adicionar(nome, xml);
  }

  iniciarServidor();
})();
