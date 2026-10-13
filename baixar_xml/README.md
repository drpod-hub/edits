# baixar_xml

Baixa arquivos XML em lote a partir de uma lista de links ou de uma página que tenha links para XML.
Só precisa de Python 3 (nada para instalar).

## Uso

```bash
# 1) Lista de links: crie um links.txt com uma URL por linha (linhas com # são ignoradas)
python baixar_xml.py -l links.txt

# 2) Varre uma página e baixa todos os links terminados em .xml
python baixar_xml.py -p https://site.com/arquivos/

# 3) URLs direto no comando
python baixar_xml.py https://site.com/a.xml https://site.com/b.xml
```

Opções úteis:

| Opção | O que faz |
|---|---|
| `-o PASTA` | pasta de destino (padrão `xmls`) |
| `-j N` | quantos downloads ao mesmo tempo (padrão 4) |
| `--filtro REGEX` | filtro dos links da página (padrão `\.xml$`; ex.: `\.xml$|download\.php`) |
| `--sobrescrever` | baixa de novo arquivos que já existem |
| `--sem-validar` | não verifica se o conteúdo é XML válido |
| `--tentativas N` | tentativas por arquivo em caso de falha de rede (padrão 3) |

## O que ele faz sozinho

- Pula arquivos que já foram baixados, então dá para rodar de novo sem duplicar.
- Remove links repetidos e tenta de novo quando a rede falha.
- Confere se o arquivo baixado é XML de verdade (e não uma página de erro).
- Salva os links que falharam em `PASTA/erros.txt`.

## Sobre captcha

O programa não resolve nem contorna captcha. Se um site exigir captcha, o link aparece como erro
com essa mensagem. Funciona com links públicos e diretos para os arquivos.
