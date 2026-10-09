// Comunicação com a SEFAZ (Ambiente Nacional): Distribuição de DF-e e evento de Ciência da Operação.
const https = require('https');
const tls = require('tls');
const fs = require('fs');
const zlib = require('zlib');
const crypto = require('crypto');

const URLS = {
  1: {
    dist: 'https://www1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx',
    evento: 'https://www.nfe.fazenda.gov.br/NFeRecepcaoEvento4/NFeRecepcaoEvento4.asmx',
  },
  2: {
    dist: 'https://hom1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx',
    evento: 'https://hom1.nfe.fazenda.gov.br/NFeRecepcaoEvento4/NFeRecepcaoEvento4.asmx',
  },
};
const NS_NFE = 'http://www.portalfiscal.inf.br/nfe';
const NS_DSIG = 'http://www.w3.org/2000/09/xmldsig#';
const WSDL_DIST = 'http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe';
const WSDL_EVENTO = 'http://www.portalfiscal.inf.br/nfe/wsdl/NFeRecepcaoEvento4';

// ---------- XML (respostas simples da SEFAZ) ----------
const tag = (xml, nome) => {
  const m = String(xml).match(new RegExp(`<(?:\\w+:)?${nome}(?:\\s[^>]*)?>([\\s\\S]*?)</(?:\\w+:)?${nome}>`));
  return m ? m[1].trim() : '';
};

function envelope(corpo) {
  return '<?xml version="1.0" encoding="utf-8"?>' +
    '<soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">' +
    `<soap12:Body>${corpo}</soap12:Body></soap12:Envelope>`;
}

class Sefaz {
  /**
   * @param {object} o
   * @param {object} o.cert      resultado de carregarCertificado()
   * @param {string} o.doc       CNPJ ou CPF do interessado
   * @param {number|string} o.cUF código IBGE da UF do interessado (ex.: 35)
   * @param {1|2} o.ambiente     1 = produção, 2 = homologação
   * @param {string} [o.caFile]  PEM com a cadeia ICP-Brasil (para validar o HTTPS da SEFAZ)
   * @param {boolean} [o.tlsInseguro] não validar o certificado do servidor (não recomendado)
   * @param {object} [o.urls]    substitui os endereços (testes)
   */
  constructor(o) {
    this.cert = o.cert;
    this.doc = o.doc;
    this.cUF = String(o.cUF);
    this.amb = String(o.ambiente || 1);
    this.urls = Object.assign({}, URLS[this.amb], o.urls || {});
    this.ca = o.caFile ? [...tls.rootCertificates, fs.readFileSync(o.caFile, 'utf8')] : undefined;
    this.tlsInseguro = !!o.tlsInseguro;
  }

  get tagDoc() {
    return this.doc.length === 11 ? `<CPF>${this.doc}</CPF>` : `<CNPJ>${this.doc}</CNPJ>`;
  }

  post(url, action, corpo) {
    const body = envelope(corpo);
    const u = new URL(url);
    return new Promise((resolve, reject) => {
      const req = https.request({
        hostname: u.hostname, port: u.port || 443, path: u.pathname + u.search, method: 'POST',
        key: this.cert.keyPem, cert: this.cert.certPem, ca: this.ca, rejectUnauthorized: !this.tlsInseguro,
        timeout: 60000,
        headers: {
          'Content-Type': `application/soap+xml; charset=utf-8; action="${action}"`,
          'Content-Length': Buffer.byteLength(body),
        },
      }, res => {
        const partes = [];
        res.on('data', c => partes.push(c));
        res.on('end', () => {
          const txt = Buffer.concat(partes).toString('utf8');
          if (res.statusCode >= 400 && !/cStat/.test(txt)) {
            reject(new Error(`SEFAZ respondeu HTTP ${res.statusCode}: ${tag(txt, 'Text') || txt.slice(0, 300)}`));
          } else resolve(txt);
        });
      });
      req.on('timeout', () => req.destroy(new Error('Tempo esgotado aguardando a SEFAZ.')));
      req.on('error', err => {
        if (/certificate|self.signed|unable to (get|verify)/i.test(err.message)) {
          err.message = 'Não foi possível validar o certificado HTTPS da SEFAZ (' + err.message +
            '). Instale a cadeia ICP-Brasil com "npm run cadeia" e configure SEFAZ_CA.';
        }
        reject(err);
      });
      req.end(body);
    });
  }

  // ---------- Distribuição de DF-e ----------
  async distribuicao(consulta) {
    const corpo =
      `<nfeDistDFeInteresse xmlns="${WSDL_DIST}"><nfeDadosMsg>` +
      `<distDFeInt xmlns="${NS_NFE}" versao="1.01"><tpAmb>${this.amb}</tpAmb><cUFAutor>${this.cUF}</cUFAutor>${this.tagDoc}${consulta}</distDFeInt>` +
      '</nfeDadosMsg></nfeDistDFeInteresse>';
    const resp = await this.post(this.urls.dist, `${WSDL_DIST}/nfeDistDFeInteresse`, corpo);
    const ret = tag(resp, 'retDistDFeInt') || resp;
    const docs = [];
    const re = /<(?:\w+:)?docZip\s+([^>]*)>([^<]+)<\/(?:\w+:)?docZip>/g;
    let m;
    while ((m = re.exec(ret))) {
      const attr = n => ((m[1].match(new RegExp(`${n}="([^"]*)"`)) || [])[1] || '');
      const xml = zlib.gunzipSync(Buffer.from(m[2].trim(), 'base64')).toString('utf8');
      const schema = attr('schema');
      docs.push({ nsu: attr('NSU'), schema, tipo: schema.split('_')[0], xml });
    }
    return {
      cStat: tag(ret, 'cStat'), xMotivo: tag(ret, 'xMotivo'),
      ultNSU: tag(ret, 'ultNSU'), maxNSU: tag(ret, 'maxNSU'), docs,
    };
  }

  consultarChave(chave) {
    return this.distribuicao(`<consChNFe><chNFe>${chave}</chNFe></consChNFe>`);
  }

  consultarNSU(ultNSU) {
    return this.distribuicao(`<distNSU><ultNSU>${String(ultNSU || 0).padStart(15, '0')}</ultNSU></distNSU>`);
  }

  // ---------- Manifestação: Ciência da Operação (210210) ----------
  async cienciaOperacao(chave) {
    const tpEvento = '210210', seq = 1;
    const id = `ID${tpEvento}${chave}${String(seq).padStart(2, '0')}`;
    const infEvento =
      `<infEvento Id="${id}"><cOrgao>91</cOrgao><tpAmb>${this.amb}</tpAmb>${this.tagDoc}<chNFe>${chave}</chNFe>` +
      `<dhEvento>${dataHoraBrasilia()}</dhEvento><tpEvento>${tpEvento}</tpEvento><nSeqEvento>${seq}</nSeqEvento><verEvento>1.00</verEvento>` +
      '<detEvento versao="1.00"><descEvento>Ciencia da Operacao</descEvento></detEvento></infEvento>';
    const evento = `<evento versao="1.00">${infEvento}${this.assinar(infEvento, id)}</evento>`;
    const corpo =
      `<nfeDadosMsg xmlns="${WSDL_EVENTO}"><envEvento xmlns="${NS_NFE}" versao="1.00">` +
      `<idLote>${Date.now().toString().slice(-15)}</idLote>${evento}</envEvento></nfeDadosMsg>`;
    const resp = await this.post(this.urls.evento, `${WSDL_EVENTO}/nfeRecepcaoEvento`, corpo);
    const ret = tag(resp, 'retEvento') || resp;
    const lote = tag(resp, 'retEnvEvento') || resp;
    return {
      cStatLote: tag(lote, 'cStat'),
      cStat: tag(tag(ret, 'infEvento') || ret, 'cStat'),
      xMotivo: tag(tag(ret, 'infEvento') || ret, 'xMotivo'),
      nProt: tag(ret, 'nProt'),
    };
  }

  // Assinatura XMLDSig (RSA-SHA1, C14N) exigida pela SEFAZ. O infEvento é gerado sem espaços nem
  // caracteres especiais, então a forma canônica é ele mesmo com o namespace herdado de envEvento.
  assinar(infEvento, id) {
    const canon = infEvento.replace('<infEvento ', `<infEvento xmlns="${NS_NFE}" `);
    const digest = crypto.createHash('sha1').update(canon, 'utf8').digest('base64');
    const signedInfo = (ns) =>
      `<SignedInfo${ns}><CanonicalizationMethod Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315"></CanonicalizationMethod>` +
      '<SignatureMethod Algorithm="http://www.w3.org/2000/09/xmldsig#rsa-sha1"></SignatureMethod>' +
      `<Reference URI="#${id}"><Transforms><Transform Algorithm="http://www.w3.org/2000/09/xmldsig#enveloped-signature"></Transform>` +
      '<Transform Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315"></Transform></Transforms>' +
      `<DigestMethod Algorithm="http://www.w3.org/2000/09/xmldsig#sha1"></DigestMethod><DigestValue>${digest}</DigestValue></Reference></SignedInfo>`;
    const valor = crypto.sign('sha1', Buffer.from(signedInfo(` xmlns="${NS_DSIG}"`), 'utf8'), this.cert.keyPem).toString('base64');
    return `<Signature xmlns="${NS_DSIG}">${signedInfo('')}<SignatureValue>${valor}</SignatureValue>` +
      `<KeyInfo><X509Data><X509Certificate>${this.cert.certBase64}</X509Certificate></X509Data></KeyInfo></Signature>`;
  }
}

// Horário de Brasília (UTC−3, sem horário de verão desde 2019), 1 minuto no passado
// para não ser rejeitado como "data no futuro" por diferença de relógio.
function dataHoraBrasilia(agora = new Date()) {
  const d = new Date(agora.getTime() - 3 * 3600e3 - 60e3);
  return d.toISOString().slice(0, 19) + '-03:00';
}

module.exports = { Sefaz, URLS, tag, dataHoraBrasilia };
