// Servidor do NotaVisor: serve o site e baixa XMLs de NF-e da SEFAZ usando o certificado A1.
const http = require('http');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { carregarCertificado } = require('./certificado');
const { Sefaz, tag } = require('./sefaz');

// ---------- Configuração ----------
carregarEnv(path.join(__dirname, '.env'));
const UF_IBGE = {
  RO: 11, AC: 12, AM: 13, RR: 14, PA: 15, AP: 16, TO: 17, MA: 21, PI: 22, CE: 23, RN: 24, PB: 25, PE: 26, AL: 27,
  SE: 28, BA: 29, MG: 31, ES: 32, RJ: 33, SP: 35, PR: 41, SC: 42, RS: 43, MS: 50, MT: 51, GO: 52, DF: 53,
};
const cfg = {
  porta: +(process.env.PORTA || 3000),
  host: process.env.HOST || '127.0.0.1',
  token: process.env.TOKEN_ACESSO || '',
  pfx: process.env.CERT_PFX || '',
  senha: process.env.CERT_SENHA || '',
  doc: (process.env.CNPJ || '').replace(/\D/g, ''),
  uf: (process.env.UF || '').toUpperCase(),
  ambiente: process.env.AMBIENTE === '2' ? 2 : 1,
  manifestar: process.env.MANIFESTAR_CIENCIA !== '0',
  caFile: process.env.SEFAZ_CA || '',
  tlsInseguro: process.env.SEFAZ_TLS_INSEGURO === '1',
  dados: path.resolve(__dirname, process.env.PASTA_DADOS || 'dados'),
  urls: { dist: process.env.SEFAZ_URL_DIST, evento: process.env.SEFAZ_URL_EVENTO },
};
const SITE = path.resolve(__dirname, '..');
const PASTA_XML = path.join(cfg.dados, 'xml');
const ARQ_ESTADO = path.join(cfg.dados, 'estado.json');
const UMA_HORA = 3600e3;

if (cfg.host !== '127.0.0.1' && cfg.host !== 'localhost' && !cfg.token) {
  console.error('Para aceitar conexões de fora (HOST=' + cfg.host + '), defina TOKEN_ACESSO no .env.');
  process.exit(1);
}

let sefaz = null, cert = null, erroConfig = '';
try {
  if (!cfg.pfx) throw new Error('Defina CERT_PFX e CERT_SENHA no arquivo servidor/.env.');
  cert = carregarCertificado(path.resolve(__dirname, cfg.pfx), cfg.senha);
  const doc = cfg.doc || cert.doc;
  if (!doc) throw new Error('Não achei o CNPJ/CPF no certificado: defina CNPJ no .env.');
  const cUF = UF_IBGE[cfg.uf] || +cfg.uf;
  if (!cUF) throw new Error('Defina UF no .env (sigla do estado do seu CNPJ, ex.: SP).');
  if (cert.validade < new Date()) throw new Error(`O certificado venceu em ${cert.validade.toLocaleDateString('pt-BR')}.`);
  sefaz = new Sefaz({
    cert, doc, cUF, ambiente: cfg.ambiente, caFile: cfg.caFile && path.resolve(__dirname, cfg.caFile),
    tlsInseguro: cfg.tlsInseguro, urls: Object.fromEntries(Object.entries(cfg.urls).filter(([, v]) => v)),
  });
} catch (err) {
  erroConfig = err.message;
  console.warn('Aviso: ' + erroConfig + ' O site funciona, mas sem download pela SEFAZ.');
}
if (cfg.tlsInseguro) console.warn('Aviso: SEFAZ_TLS_INSEGURO=1 — o certificado HTTPS da SEFAZ não será validado.');

fs.mkdirSync(PASTA_XML, { recursive: true });

// ---------- Estado e cache ----------
function lerEstado() {
  try { return JSON.parse(fs.readFileSync(ARQ_ESTADO, 'utf8')); } catch (_) { return {}; }
}
function salvarEstado(e) { fs.writeFileSync(ARQ_ESTADO, JSON.stringify(e, null, 2)); }

const arqXml = chave => path.join(PASTA_XML, `${chave}.xml`);
const arqResumo = chave => path.join(PASTA_XML, `${chave}.resumo.xml`);

function guardarDocumento(d) {
  const chave = tag(d.xml, 'chNFe') || (d.xml.match(/Id="NFe(\d{44})"/) || [])[1];
  if (!chave) return null;
  if (d.tipo === 'procNFe') {
    fs.writeFileSync(arqXml(chave), d.xml);
    return { chave, tipo: 'completa' };
  }
  if (d.tipo === 'resNFe') {
    if (!fs.existsSync(arqXml(chave))) fs.writeFileSync(arqResumo(chave), d.xml);
    return { chave, tipo: 'resumo' };
  }
  return { chave, tipo: d.tipo }; // eventos: não guardamos
}

function infoNota(chave) {
  const completa = fs.existsSync(arqXml(chave));
  const arq = completa ? arqXml(chave) : arqResumo(chave);
  if (!fs.existsSync(arq)) return null;
  const xml = fs.readFileSync(arq, 'utf8');
  const emit = tag(xml, 'emit') || xml;
  return {
    chave, completa,
    numero: tag(xml, 'nNF') || String(+chave.slice(25, 34)),
    emitente: tag(emit, 'xNome'),
    valor: tag(xml, 'vNF'),
    emissao: tag(xml, 'dhEmi'),
    atualizado: fs.statSync(arq).mtime,
  };
}

function bloqueio(estado, chaveBloqueio) {
  const ate = estado[chaveBloqueio];
  return ate && Date.parse(ate) > Date.now() ? ate : null;
}

// ---------- Ações ----------
async function baixarPorChave(chave) {
  if (fs.existsSync(arqXml(chave))) return { status: 'ok', origem: 'cache', xml: fs.readFileSync(arqXml(chave), 'utf8') };

  const estado = lerEstado();
  const bloq = bloqueio(estado, 'bloqueioConsultaAte');
  if (bloq) return { status: 'aguarde', ate: bloq, mensagem: 'A SEFAZ bloqueou novas consultas por consumo excessivo. Tente depois de ' + horaBR(bloq) + '.' };

  let r = await consultar(chave);
  if (r.status !== 'resumo') return r;

  if (!cfg.manifestar) {
    return Object.assign(r, { mensagem: 'A SEFAZ só devolveu o resumo. Para liberar o XML completo, é preciso registrar a Ciência da Operação (MANIFESTAR_CIENCIA=1).' });
  }
  const ev = await sefaz.cienciaOperacao(chave);
  // 135 = evento registrado; 573 = já havia ciência registrada.
  if (!['135', '136', '573'].includes(ev.cStat)) {
    return Object.assign(r, { mensagem: `A SEFAZ recusou a Ciência da Operação: ${ev.cStat} - ${ev.xMotivo}` });
  }
  await esperar(4000);
  const r2 = await consultar(chave);
  if (r2.status === 'resumo') {
    return Object.assign(r2, { mensagem: 'Ciência da Operação registrada. A SEFAZ costuma liberar o XML completo em alguns minutos: tente de novo mais tarde.' });
  }
  return r2;
}

async function consultar(chave) {
  const r = await sefaz.consultarChave(chave);
  if (r.cStat === '656') {
    const estado = lerEstado();
    estado.bloqueioConsultaAte = new Date(Date.now() + UMA_HORA).toISOString();
    salvarEstado(estado);
    return { status: 'aguarde', ate: estado.bloqueioConsultaAte, mensagem: `${r.cStat} - ${r.xMotivo}. A SEFAZ pede uma hora de espera.` };
  }
  if (r.cStat !== '138') return { status: 'erro', cStat: r.cStat, mensagem: `${r.cStat} - ${r.xMotivo}` };
  r.docs.forEach(guardarDocumento);
  const proc = r.docs.find(d => d.tipo === 'procNFe');
  if (proc) return { status: 'ok', origem: 'sefaz', xml: proc.xml };
  const res = r.docs.find(d => d.tipo === 'resNFe');
  if (res) return { status: 'resumo', resumo: resumoNFe(res.xml) };
  return { status: 'erro', mensagem: 'A SEFAZ não devolveu a nota (só eventos).' };
}

function resumoNFe(xml) {
  const sit = { 1: 'Autorizada', 2: 'Denegada', 3: 'Cancelada' };
  return {
    chave: tag(xml, 'chNFe'), emitente: tag(xml, 'xNome'), cnpj: tag(xml, 'CNPJ') || tag(xml, 'CPF'),
    emissao: tag(xml, 'dhEmi'), valor: tag(xml, 'vNF'), protocolo: tag(xml, 'nProt'),
    situacao: sit[tag(xml, 'cSitNFe')] || tag(xml, 'cSitNFe'),
  };
}

// Busca, pelo NSU, tudo o que foi emitido contra o CNPJ desde a última sincronização.
async function sincronizar() {
  const estado = lerEstado();
  const bloq = bloqueio(estado, 'proximaSincronizacao') || bloqueio(estado, 'bloqueioConsultaAte');
  if (bloq) return { status: 'aguarde', ate: bloq, mensagem: 'A SEFAZ só permite nova sincronização depois de ' + horaBR(bloq) + '.' };

  let ult = estado.ultNSU || '0', novas = [], resumos = [], voltas = 0, r;
  do {
    r = await sefaz.consultarNSU(ult);
    if (r.cStat === '656') {
      estado.bloqueioConsultaAte = new Date(Date.now() + UMA_HORA).toISOString();
      break;
    }
    if (!['137', '138'].includes(r.cStat)) {
      salvarEstado(estado);
      return { status: 'erro', mensagem: `${r.cStat} - ${r.xMotivo}`, novas, resumos };
    }
    for (const d of r.docs) {
      const g = guardarDocumento(d);
      if (g && g.tipo === 'completa') novas.push(g.chave);
      if (g && g.tipo === 'resumo') resumos.push(g.chave);
    }
    ult = r.ultNSU || ult;
    estado.ultNSU = ult;
    salvarEstado(estado);
    voltas++;
  } while (r.cStat === '138' && r.ultNSU !== r.maxNSU && voltas < 20);

  // Regra da SEFAZ: ao chegar ao fim da fila (137 ou ultNSU = maxNSU), esperar 1 hora.
  if (r.cStat === '137' || r.ultNSU === r.maxNSU) estado.proximaSincronizacao = new Date(Date.now() + UMA_HORA).toISOString();
  salvarEstado(estado);

  // Resumos (notas sem ciência ainda): registra a ciência para que o XML venha na próxima sincronização.
  let ciencias = 0;
  if (cfg.manifestar) {
    for (const chave of resumos.filter(c => !fs.existsSync(arqXml(c)))) {
      try {
        const ev = await sefaz.cienciaOperacao(chave);
        if (['135', '136', '573'].includes(ev.cStat)) ciencias++;
      } catch (_) { /* tenta de novo na próxima sincronização */ }
    }
  }
  return {
    status: r.cStat === '656' ? 'aguarde' : 'ok', novas, resumos, ciencias, ultNSU: ult,
    proxima: estado.proximaSincronizacao || null,
    mensagem: r.cStat === '656' ? `${r.cStat} - ${r.xMotivo}` : '',
  };
}

// ---------- HTTP ----------
const TIPOS = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.xml': 'application/xml', '.svg': 'image/svg+xml', '.png': 'image/png', '.ico': 'image/x-icon' };

function json(res, codigo, obj) {
  res.writeHead(codigo, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
  res.end(JSON.stringify(obj));
}

function autorizado(req) {
  if (!cfg.token) return true;
  const recebido = (req.headers.authorization || '').replace(/^Bearer\s+/i, '');
  const a = Buffer.from(recebido), b = Buffer.from(cfg.token);
  return a.length === b.length && crypto.timingSafeEqual(a, b);
}

function lerCorpo(req) {
  return new Promise((resolve, reject) => {
    let s = '';
    req.on('data', c => { s += c; if (s.length > 1e5) req.destroy(); });
    req.on('end', () => { try { resolve(s ? JSON.parse(s) : {}); } catch (e) { reject(new Error('JSON inválido')); } });
    req.on('error', reject);
  });
}

function servirArquivo(req, res) {
  const rel = decodeURIComponent(new URL(req.url, 'http://x').pathname);
  let arq = path.normalize(path.join(SITE, rel === '/' ? 'index.html' : rel));
  // Nunca expor a pasta do servidor (certificado, .env, XMLs baixados).
  if (!arq.startsWith(SITE + path.sep) || arq.startsWith(__dirname + path.sep) || arq === __dirname) {
    res.writeHead(404); return res.end('Não encontrado');
  }
  fs.stat(arq, (err, st) => {
    if (!err && st.isDirectory()) arq = path.join(arq, 'index.html');
    fs.readFile(arq, (err2, buf) => {
      if (err2) { res.writeHead(404); return res.end('Não encontrado'); }
      res.writeHead(200, { 'Content-Type': TIPOS[path.extname(arq)] || 'application/octet-stream' });
      res.end(buf);
    });
  });
}

const servidor = http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://x');
  if (!url.pathname.startsWith('/api/')) return servirArquivo(req, res);

  if (url.pathname === '/api/status') {
    return json(res, 200, {
      ativo: !!sefaz, erro: erroConfig, precisaToken: !!cfg.token,
      titular: cert ? cert.nome : '', doc: sefaz ? sefaz.doc : '', validade: cert ? cert.validade : null,
      ambiente: cfg.ambiente === 2 ? 'homologação' : 'produção', manifestar: cfg.manifestar,
    });
  }
  if (!autorizado(req)) return json(res, 401, { erro: 'Token de acesso inválido.' });
  if (!sefaz) return json(res, 503, { erro: erroConfig });

  try {
    if (req.method === 'POST' && url.pathname === '/api/baixar') {
      const { chave } = await lerCorpo(req);
      const c = String(chave || '').replace(/\D/g, '');
      if (!/^\d{44}$/.test(c)) return json(res, 400, { erro: 'Informe uma chave de 44 dígitos.' });
      if (c.slice(20, 22) !== '55') return json(res, 400, { erro: 'O download pela SEFAZ funciona só para NF-e (modelo 55).' });
      const r = await baixarPorChave(c);
      return json(res, r.status === 'ok' ? 200 : r.status === 'aguarde' ? 429 : r.status === 'resumo' ? 202 : 422, r);
    }
    if (req.method === 'POST' && url.pathname === '/api/sincronizar') {
      const r = await sincronizar();
      return json(res, r.status === 'erro' ? 502 : r.status === 'aguarde' ? 429 : 200, r);
    }
    if (req.method === 'GET' && url.pathname === '/api/notas') {
      const chaves = [...new Set(fs.readdirSync(PASTA_XML).map(f => (f.match(/^(\d{44})/) || [])[1]).filter(Boolean))];
      const notas = chaves.map(infoNota).filter(Boolean).sort((a, b) => String(b.emissao).localeCompare(String(a.emissao)));
      return json(res, 200, { notas });
    }
    const m = url.pathname.match(/^\/api\/notas\/(\d{44})$/);
    if (req.method === 'GET' && m) {
      if (!fs.existsSync(arqXml(m[1]))) return json(res, 404, { erro: 'XML completo ainda não baixado.' });
      res.writeHead(200, { 'Content-Type': 'application/xml; charset=utf-8' });
      return res.end(fs.readFileSync(arqXml(m[1])));
    }
    return json(res, 404, { erro: 'Rota não encontrada.' });
  } catch (err) {
    console.error(err);
    return json(res, 502, { erro: 'Falha ao falar com a SEFAZ: ' + err.message });
  }
});

servidor.listen(cfg.porta, cfg.host, () => {
  console.log(`NotaVisor em http://${cfg.host === '0.0.0.0' ? 'localhost' : cfg.host}:${cfg.porta}`);
  if (sefaz) console.log(`Certificado: ${cert.nome} (${sefaz.doc}) — ambiente de ${cfg.ambiente === 2 ? 'homologação' : 'produção'}`);
});

// ---------- Utilidades ----------
function esperar(ms) { return new Promise(r => setTimeout(r, ms)); }
function horaBR(iso) { return new Date(iso).toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo' }); }
function carregarEnv(arq) {
  if (!fs.existsSync(arq)) return;
  for (const linha of fs.readFileSync(arq, 'utf8').split(/\r?\n/)) {
    const m = linha.match(/^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*?)\s*$/);
    if (m && !(m[1] in process.env)) process.env[m[1]] = m[2].replace(/^(['"])(.*)\1$/, '$2');
  }
}
