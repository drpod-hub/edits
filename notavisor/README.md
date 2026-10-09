# NotaVisor

Visualizador de DANFE a partir do XML de **NF-e**, **NFC-e** e **CT-e**, feito para rodar só no navegador. Os arquivos nunca saem do computador do usuário.

## Funções

- **Abrir XML**: arrastar e soltar, escolher arquivos (vários de uma vez) ou colar o conteúdo.
- **DANFE NF-e** em A4: canhoto, código de barras da chave, destinatário, fatura e duplicatas, impostos (inclusive IBS/CBS quando houver), transporte, itens e dados adicionais.
- **DANFE NFC-e** em bobina de 80 mm, com QR Code.
- **Resumo do CT-e**, para conferência.
- Marca d'água automática quando a nota é de homologação, está cancelada (se o evento vier no arquivo), não tem protocolo ou não foi autorizada.
- **Imprimir / Salvar PDF**, **Baixar XML**, **Copiar chave** e link para a consulta oficial da SEFAZ.
- **Consultar chave**: valida o dígito verificador (inclusive com CNPJ alfanumérico) e mostra o que a chave informa (UF, mês, CNPJ, modelo, série, número e tipo de emissão).

## Rodar

É um site estático, sem build. Abra `index.html` no navegador ou publique a pasta em qualquer hospedagem estática (GitHub Pages, Netlify, Vercel...).

```bash
cd notavisor && python3 -m http.server 8000   # http://localhost:8000
```

A única dependência externa é a biblioteca de QR Code (`qrcode-generator`, via cdnjs). Sem internet, o DANFE da NFC-e mostra a URL do QR em texto.

## Baixar XML da SEFAZ com certificado A1 (opcional)

A pasta `servidor/` traz um servidor Node que usa o **certificado A1** da empresa no serviço oficial **Distribuição de DF-e** da SEFAZ (Ambiente Nacional). Ele não usa captcha. Com o servidor rodando, a aba *Consultar chave* ganha:

- **Baixar XML com meu certificado**: baixa a NF-e pela chave e já abre o DANFE.
- **Buscar notas novas**: puxa tudo o que foi emitido contra o seu CNPJ desde a última busca.

Só funciona para **NF-e (modelo 55)** em que o CNPJ do certificado é **destinatário**, **transportador** ou está **autorizado no XML**. Não dá para baixar a nota de outra empresa, nem NFC-e. A SEFAZ guarda as notas para download por cerca de 3 meses.

### Instalação

```bash
cd notavisor/servidor
npm install
npm run cadeia            # baixa a cadeia ICP-Brasil (valida o HTTPS da SEFAZ)
cp .env.exemplo .env      # preencha CERT_PFX, CERT_SENHA e UF
# copie o certificado .pfx para esta pasta
npm start                 # http://127.0.0.1:3000
```

### Como funciona

1. Consulta a chave na Distribuição de DF-e (`consChNFe`).
2. Se a SEFAZ devolver só o **resumo**, registra automaticamente o evento **Ciência da Operação (210210)**, assinado com o certificado, e consulta de novo. A ciência não aceita nem recusa a nota: só informa que você tomou conhecimento dela. Para desligar, use `MANIFESTAR_CIENCIA=0`.
3. Salva o XML em `servidor/dados/xml/` e entrega ao navegador. Consultas repetidas usam esse cache e não gastam cota da SEFAZ.

Regras de uso da SEFAZ que o servidor respeita: após `137` (nenhum documento novo), uma nova busca só depois de 1 hora. Após `656` (consumo indevido), o servidor bloqueia novas consultas por 1 hora.

### Segurança

- Por padrão, o servidor só aceita conexões da própria máquina (`HOST=127.0.0.1`). Para abrir na rede, ele exige `TOKEN_ACESSO`. Mesmo assim, use HTTPS (um proxy reverso, por exemplo).
- O certificado, a senha e os XMLs ficam no servidor, nunca no navegador. `.env`, `*.pfx`, `dados/` e `icp-brasil.pem` estão no `.gitignore`.
- O HTTPS da SEFAZ é validado pela cadeia ICP-Brasil. `SEFAZ_TLS_INSEGURO=1` desliga a validação, mas só deve ser usado para diagnóstico.

## Limitações

- Sem o servidor, baixar o XML só com a chave não é possível: use o portal da SEFAZ, que tem captcha.
- O servidor foi testado com uma SEFAZ simulada (mTLS, distribuição por chave e por NSU, evento assinado e validado com outra biblioteca). Faça o primeiro teste em homologação (`AMBIENTE=2`).
- Notas com muitos itens continuam em mais de uma página: o cabeçalho da tabela se repete, mas o bloco do emitente não.

## Arquivos

| Arquivo | O que faz |
|---|---|
| `nfe.js` | leitura do XML e validação da chave de acesso |
| `danfe.js` | layout do DANFE (NF-e, NFC-e) e do resumo do CT-e |
| `barcode.js` | código de barras Code 128 em SVG |
| `app.js` | interface |
| `exemplos/exemplos.js` | notas fictícias (homologação) para teste |
| `servidor/` | servidor opcional com certificado A1 (Distribuição de DF-e e Ciência da Operação) |
