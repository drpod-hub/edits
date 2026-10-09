// Baixa as ACs da ICP-Brasil (site oficial do ITI) e grava icp-brasil.pem,
// usado para validar o certificado HTTPS dos servidores da SEFAZ.
const https = require('https');
const fs = require('fs');
const path = require('path');
const { X509Certificate } = require('crypto');
const AdmZip = require('adm-zip');

const URL_CADEIA = process.env.URL_CADEIA || 'https://acraiz.icpbrasil.gov.br/credenciadas/CertificadosAC-ICP-Brasil/ACcompactado.zip';
const SAIDA = path.join(__dirname, 'icp-brasil.pem');

function baixar(url, redirecionamentos = 5) {
  return new Promise((resolve, reject) => {
    https.get(url, res => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location && redirecionamentos > 0) {
        res.resume();
        return resolve(baixar(new URL(res.headers.location, url).toString(), redirecionamentos - 1));
      }
      if (res.statusCode !== 200) return reject(new Error(`HTTP ${res.statusCode} ao baixar ${url}`));
      const partes = [];
      res.on('data', c => partes.push(c));
      res.on('end', () => resolve(Buffer.concat(partes)));
    }).on('error', reject);
  });
}

(async () => {
  console.log('Baixando ' + URL_CADEIA);
  const zip = new AdmZip(await baixar(URL_CADEIA));
  const pems = [];
  for (const e of zip.getEntries()) {
    if (e.isDirectory) continue;
    try {
      // Os arquivos vêm em DER ou PEM; X509Certificate aceita os dois.
      pems.push(new X509Certificate(e.getData()).toString().trim());
    } catch (_) { /* não é certificado */ }
  }
  if (!pems.length) throw new Error('Nenhum certificado encontrado no pacote.');
  fs.writeFileSync(SAIDA, pems.join('\n') + '\n');
  console.log(`${pems.length} certificados gravados em ${SAIDA}`);
})().catch(err => { console.error('Erro: ' + err.message); process.exit(1); });
