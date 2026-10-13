# Baixar XML de NF-e pela chave de acesso

Baixa o XML completo (`procNFe`) de notas fiscais eletrônicas usando só as chaves de acesso, pelo
web service oficial **NFeDistribuicaoDFe** da SEFAZ (consulta `consChNFe`).

## Requisitos

- Python 3.8+ e `pip install requests cryptography`
- **Certificado digital A1 (.pfx)** de uma empresa que seja parte da nota (emitente, destinatário
  ou transportador). A SEFAZ só entrega o XML para quem é parte da nota.

## Uso

```bash
# chaves num arquivo (uma por linha, ou CSV/texto qualquer: as chaves de 44 dígitos são extraídas)
python3 baixar_xml.py --pfx empresa.pfx --uf SP chaves.txt

# ou chaves direto na linha de comando
python3 baixar_xml.py --pfx empresa.pfx --uf SP 3524...0001 3524...0002
```

| Opção | Para quê |
|---|---|
| `--senha` | senha do certificado (se omitida, é pedida no terminal) |
| `--uf` | UF da empresa do certificado |
| `--cnpj` | CNPJ/CPF interessado (padrão: lido do certificado) |
| `--saida` | pasta dos XMLs (padrão `xmls/`) |
| `--intervalo` | segundos entre consultas (padrão 2) |
| `--homologacao` | usa o ambiente de testes |

Os arquivos saem como `CHAVE-procNFe.xml`. Chaves que falharem vão para `xmls/falhas.txt`, para
você rodar de novo só com elas.

## Observações

- **Veio só o resumo (`CHAVE-resumo.xml`)?** Acontece quando você é o destinatário e ainda não
  manifestou a nota. Faça a manifestação "Ciência da Operação" (no seu ERP ou no portal) e rode de novo.
- **cStat 656 (consumo indevido):** a SEFAZ bloqueia por cerca de 1 hora quando há consultas
  demais. O programa para e salva as chaves restantes em `falhas.txt`.
- Só funciona para **NF-e modelo 55**. NFC-e (65) e CT-e não estão nesse serviço.
- A chave é validada (44 dígitos + dígito verificador) antes de consultar.
