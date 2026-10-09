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

## Limitações

- Baixar o XML apenas com a chave não é possível sem certificado digital A1 ou uma API paga (Focus NFe, NFe.io, Qive etc.). Para isso, seria preciso um backend.
- Notas com muitos itens continuam em mais de uma página: o cabeçalho da tabela se repete, mas o bloco do emitente não.

## Arquivos

| Arquivo | O que faz |
|---|---|
| `nfe.js` | leitura do XML e validação da chave de acesso |
| `danfe.js` | layout do DANFE (NF-e, NFC-e) e do resumo do CT-e |
| `barcode.js` | código de barras Code 128 em SVG |
| `app.js` | interface |
| `exemplos/exemplos.js` | notas fictícias (homologação) para teste |
