// Leitura do certificado A1 (.pfx/.p12) e extração de chave, certificado e CNPJ/CPF.
const fs = require('fs');
const forge = require('node-forge');

function carregarCertificado(caminho, senha) {
  const der = fs.readFileSync(caminho).toString('binary');
  let p12;
  try {
    p12 = forge.pkcs12.pkcs12FromAsn1(forge.asn1.fromDer(der), senha || '');
  } catch (err) {
    throw new Error('Não foi possível abrir o certificado: confira o arquivo e a senha. (' + err.message + ')');
  }

  const bags = t => (p12.getBags({ bagType: t })[t] || []);
  const keyBag = bags(forge.pki.oids.pkcs8ShroudedKeyBag)[0] || bags(forge.pki.oids.keyBag)[0];
  if (!keyBag) throw new Error('O certificado não contém chave privada.');
  const key = keyBag.key;

  // O .pfx costuma trazer a cadeia junto: pegamos o certificado que corresponde à chave.
  const certs = bags(forge.pki.oids.certBag).map(b => b.cert).filter(Boolean);
  const cert = certs.find(c => c.publicKey.n && c.publicKey.n.equals(key.n)) || certs[0];
  if (!cert) throw new Error('O arquivo não contém o certificado.');

  const cn = (cert.subject.getField('CN') || {}).value || '';
  // ICP-Brasil: CN = "RAZÃO SOCIAL:CNPJ" (e-CNPJ) ou "NOME:CPF" (e-CPF).
  const doc = (cn.match(/:(\d{14}|\d{11})$/) || [])[1] || '';
  const certDer = forge.asn1.toDer(forge.pki.certificateToAsn1(cert)).getBytes();

  return {
    keyPem: forge.pki.privateKeyToPem(key),
    certPem: forge.pki.certificateToPem(cert),
    certBase64: forge.util.encode64(certDer),
    nome: cn.replace(/:\d+$/, ''),
    doc,
    validade: cert.validity.notAfter,
  };
}

module.exports = { carregarCertificado };
