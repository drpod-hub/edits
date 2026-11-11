---
name: estoque-fiscal-dominio
description: Monta o estoque fiscal (inventario) de uma empresa a partir de XMLs de NF-e/NFC-e, relatorios do Dominio ou planilha de contagem do cliente, calcula o custo conforme o regime tributario (Simples, Presumido, Real) e entrega a planilha Excel do inventario, o Livro Registro de Inventario (modelo P7, em PDF) e o arquivo para importar o saldo de estoque no Dominio (Bloco H). Use sempre que o usuario falar em estoque fiscal, inventario, estoque final, estoque de fechamento, Registro de Inventario, Bloco H, saldo de estoque, CMV que nao fecha, ou pedir para levantar, calcular, valorar, ajustar ou importar o estoque de um cliente, mesmo que nao use a palavra "inventario".
---

# Estoque fiscal → inventário, Livro P7 e importação no Domínio

Esta skill levanta o inventário de fechamento de um cliente do escritório. Um script faz a parte mecânica (ler notas, calcular custo, movimentar item a item, gerar os arquivos) e você cuida do que exige julgamento: escolher o método, ligar o produto do fornecedor ao produto da empresa, tratar unidades diferentes e decidir o que não é estoque.

Scripts, na pasta `scripts/` ao lado deste arquivo:
- `scripts/estoque.py`: comandos `ler-xml`, `ler-planilha`, `apurar`, `conferir`, `gerar`;
- `scripts/saidas.py`: usado pelo `gerar` (Excel, PDF, Domínio, SPED).

Chame sempre pelo caminho completo, ex.: `python3 <pasta_da_skill>/scripts/estoque.py ...`, e grave tudo numa pasta de trabalho (ex.: `/tmp/estoque/<cliente>`). Precisa de `openpyxl` e `reportlab`.

Se a pasta `scripts/` não existir (skill instalada só com este arquivo), faça o mesmo trabalho com um código Python seu, seguindo as regras de custo e os formatos descritos aqui, e avise o usuário que com os scripts o processo fica mais rápido e mais seguro.

## Passo 1 – Confirmar os dados do trabalho

Pergunte só o que não estiver claro:
1. **Empresa**: razão social, CNPJ, inscrição estadual e código no Domínio.
2. **Data do inventário** (normalmente 31/12) e o período das notas.
3. **Regime tributário**: Simples, Presumido ou Real. Ele define o custo (Passo 4).
4. **Atividade**: comércio ou indústria. Na indústria a matéria-prima comprada não é o produto vendido, então a movimentação por item não funciona sem ficha de produção: use contagem ou valor alvo.
5. **O que o cliente tem**: XMLs de entrada e de saída? Inventário do ano anterior? Contagem física? Um valor de estoque que precisa fechar?
6. **Método** (veja abaixo). Se o usuário não disser, proponha um pelo que ele enviou e confirme antes de apurar.

### Escolha do método

| Situação | Método | O que precisa |
|---|---|---|
| Comércio com XML de compras **e** de vendas (NF-e e NFC-e) | `movimentacao` | movimentos + inventário anterior, se houver |
| Cliente fez contagem física | `contagem` | planilha de contagem + notas de entrada para dar o custo |
| Sem controle de estoque; existe um valor a fechar (saldo contábil, CMV esperado) | `alvo` | notas de entrada + o valor |

A contagem física é sempre a melhor evidência. Quando ela existir, prefira `contagem`, mesmo havendo XML.

## Passo 2 – Ler as fontes

**XMLs de NF-e/NFC-e** (pastas, arquivos soltos ou `.zip`):
```
python3 <pasta>/scripts/estoque.py ler-xml PASTA_OU_ZIP [outras...] --cnpj CNPJ --de 01/01/2025 --ate 31/12/2025 --saida /tmp/estoque/cli
```
Gera `movimentos.csv`, uma linha por item de nota. O script descarta canceladas e denegadas, define entrada/saída pelo CNPJ e classifica cada item pelo CFOP na coluna `movimenta`: `S` mexe no estoque, `N` não mexe, `R` revisar.

Leia o resumo impresso e resolva antes de seguir:
- **Fornecedores tratados como compra para estoque.** A nota do fornecedor traz o CFOP *dele* (5102), que não diz se a empresa comprou para revender, usar ou imobilizar. Mostre a lista ao usuário e pergunte quais são uso e consumo ou imobilizado; exclua-os no `apurar` com `--excluir-fornecedores CNPJ1,CNPJ2`, ou troque `movimenta` para `N` nas linhas.
- **Linhas `R`** (CFOP x949 e parecidos): decida `S` ou `N` na coluna `movimenta`, perguntando ao usuário quando não der para saber.
- **Nenhuma nota de saída**: sem as vendas a movimentação não fecha. Peça os XMLs de venda ou mude de método.
- O script só enxerga cancelamento que esteja no XML (protocolo ou evento). Se a pasta tiver só os XMLs de autorização, avise que notas canceladas depois podem estar contadas.
- Remessas e retornos (conserto, demonstração, depósito) ficam como `N`: a mercadoria continua sendo da empresa.

**Planilha do cliente, inventário anterior ou relatório do Domínio em Excel/CSV:**
```
python3 <pasta>/scripts/estoque.py ler-planilha ARQUIVO.xlsx --saida /tmp/estoque/cli/contagem.csv
```
O script acha a linha de cabeçalho e as colunas pelo nome e mostra o mapeamento. **Confira o mapeamento impresso**; se errou, repita com `--linha-cabecalho N` e `--mapa campo=COLUNA` (letra ou nome do cabeçalho; campos: `codigo, descricao, ncm, unidade, quantidade, custo_unitario, valor_total, ean, grupo`). Use `--aba NOME` para outra aba.

**Relatório do Domínio em PDF** (entradas/saídas por produto, inventário anterior): não há leitor pronto, porque o leiaute varia conforme o relatório. Leia o PDF, transcreva para CSV no formato padrão e confira o total com o do relatório antes de usar:
- inventário (saldo inicial ou contagem): `codigo;descricao;ncm;unidade;quantidade;custo_unitario;valor_total`
- movimentos: no mínimo `data;tipo;natureza;movimenta;numero;cfop;codigo;descricao;ncm;unidade;quantidade;valor_produtos`, com `tipo` E/S, `movimenta` S e `natureza` em `compra, devolucao_venda, transf_entrada, bonificacao, venda, devolucao_compra, transf_saida, outras_saidas`. Se o relatório já trouxer o custo de aquisição, grave-o em `custo_informado` (valor total da linha) e o script usa esse valor em vez de calcular.

Os CSV usam `;`, vírgula decimal e abrem direto no Excel.

## Passo 3 – Apurar

```
python3 <pasta>/scripts/estoque.py apurar --metodo movimentacao --regime simples \
  --movimentos /tmp/estoque/cli/movimentos.csv --inicial inventario_2024.csv \
  --data 31/12/2025 --saida /tmp/estoque/cli/apuracao
```
Saídas na pasta: `inventario.csv`, `pendencias.csv`, `ficha_movimentacao.csv` (kardex), `movimentos_vinculados.csv` e `premissas.json`.

- **`movimentacao`**: saldo inicial + entradas − saídas, por item, a **custo médio ponderado móvel**. Devolução de venda volta ao custo médio (não ao preço de venda); devolução de compra sai ao custo médio.
- **`contagem`**: `--contagem contagem.csv --custo medio|ultima|planilha`. Usa as quantidades do cliente e busca o custo nas entradas (por código, EAN ou descrição). `planilha` usa o custo que veio na própria contagem.
- **`alvo`**: `--alvo 150000,00`. Critério padrão `ultimas-compras`: percorre as compras da mais recente para a mais antiga até somar o valor, no raciocínio de que o que sobrou em estoque é o que foi comprado por último. Alternativa: `--criterio proporcional --base inventario.csv`, que escala as quantidades de um inventário existente. As quantidades de itens em UN/PC/CX ficam inteiras, então pode sobrar uma pequena diferença, que o script informa; `--exato` permite fração para chegar mais perto.

Opções comuns: `--depara depara.csv`, `--excluir-fornecedores`, `--data` (ignora notas posteriores).

### O resumo é o seu teste de sanidade
O script imprime estoque inicial, compras líquidas, estoque final, CMV e CMV/vendas. Olhe esses números antes de qualquer outra coisa:
- CMV negativo ou maior que as vendas quase sempre é vínculo errado, unidade sem conversão ou nota faltando;
- CMV/vendas muito diferente da margem normal do ramo (ou do ano anterior do cliente) merece uma pergunta ao usuário.
Não entregue um inventário cujo CMV você não saberia explicar.

## Passo 4 – Custo conforme o regime

O custo de cada entrada é: produtos − desconto + frete + seguro + outras despesas + II + ICMS-ST/FCP-ST, menos os impostos que a empresa recupera. O `--regime` define o padrão:

| Regime | ICMS próprio | PIS/COFINS | IPI |
|---|---|---|---|
| `simples` | fica no custo | fica no custo | fica no custo |
| `presumido` | sai do custo (crédito) | fica no custo | fica no custo |
| `real` | sai do custo (crédito) | sai do custo (9,25%) | fica no custo |

Regras que o script aplica e que você deve conhecer para explicar ao usuário:
- **ICMS-ST nunca é crédito**: entra no custo, e nesses itens (CST 10/30/60/70, CSOSN 201/202/203/500) o ICMS próprio também não é abatido.
- Compra de fornecedor do Simples: o crédito de ICMS é o `vCredICMSSN` destacado na nota, quando houver.
- PIS/COFINS no Lucro Real: o crédito é calculado pela alíquota (`--aliq-piscofins`, padrão 9,25) sobre o valor de aquisição sem o ICMS, e não é tomado quando o CST de PIS da nota indica monofásico, alíquota zero, isenção ou suspensão (04 a 09).
- IPI só sai do custo com `--ipi-recuperavel sim` (indústria ou equiparada).

Ajuste quando o caso fugir do padrão: `--icms-recuperavel nao` para empresa do Presumido que não é contribuinte do ICMS; `--piscofins-recuperavel nao` para empresa do Real com receita no regime cumulativo. Na dúvida sobre o enquadramento, pergunte: é uma decisão do contador, não do script. As premissas usadas ficam gravadas em `premissas.json` e vão para a aba Resumo do Excel.

Os scripts não tratam IBS/CBS. Para inventários em que a CBS já substitui PIS/COFINS, avise o usuário e revise o custo com ele.

## Passo 5 – Resolver as pendências

Abra `pendencias.csv`. Cada tipo pede uma ação:

- **`vinculo`**: a entrada veio com o código do fornecedor e o script não achou o produto da empresa (tentou de-para, EAN e descrição idêntica). Ela entrou com um código provisório (o EAN ou `F<cnpj>-<código>`), ou seja, compra e venda do mesmo produto ficaram em itens separados. Analise as sugestões da coluna `detalhe`, monte o `depara.csv` e apure de novo:
  ```
  cnpj_fornecedor;codigo_origem;codigo;fator
  99888777000166;F-SAB;004;1
  ```
  Vincule só quando tiver certeza de que é o mesmo produto (marca, tamanho, sabor). Na dúvida, liste para o usuário. Se a empresa não emite nota por item (não há cadastro próprio), os códigos provisórios podem ficar: diga isso no resumo.
- **`unidade`**: compra em CX e venda em UN, por exemplo. Informe o `fator` no de-para (unidades da empresa por unidade da nota; caixa com 12 → `12`). Quando a nota traz a unidade tributável igual à da empresa, o script já converte sozinho e registra na observação: confira esses casos por amostragem.
- **`saldo_negativo`**: saiu mais do que entrou. Causas comuns, nesta ordem: vínculo ou fator faltando, saldo inicial não informado, nota de entrada que não veio. O item fica fora do inventário (saldo zero). Liste os mais relevantes para o usuário; não invente entrada para cobrir.
- **`sem_custo`**: item sem nenhuma entrada que dê custo (comum na contagem). Peça a nota de compra ou o custo ao usuário. Não use preço de venda como custo.

Guarde o `depara.csv` e entregue ao usuário: ele serve para o próximo ano do mesmo cliente.

## Passo 6 – Conferir e gerar

```
python3 <pasta>/scripts/estoque.py conferir /tmp/estoque/cli/apuracao/inventario.csv
python3 <pasta>/scripts/estoque.py gerar /tmp/estoque/cli/apuracao/inventario.csv \
  --empresa "RAZAO SOCIAL" --cnpj 11222333000181 --ie 123456789 --codigo-empresa 178 \
  --data 31/12/2025 --pasta-trabalho /tmp/estoque/cli/apuracao \
  --modelo-dominio modelo_dominio.xlsx --saida /tmp/estoque/cli/entrega
```
`conferir` acusa erro para código repetido, quantidade ou custo zerado, e aviso para NCM fora de 8 dígitos. `gerar` não roda com erro (há `--forcar`, só com o aval do usuário). Você pode editar o `inventario.csv` à mão antes de gerar; a coluna `grupo` é o tipo do item (00 revenda, 01 matéria-prima, 02 embalagem, 03 em processo, 04 produto acabado, 07 uso e consumo) e separa os blocos do Livro.

Arquivos gerados (`--formatos excel,livro,dominio`, com `sped` opcional), com o nome `<código da empresa>_<AAAAMMDD>_...`:
- **`_inventario.xlsx`**: abas Inventário, Resumo (premissas, CMV, totais por grupo), Pendências e Ficha de movimentação;
- **`_livro_registro_inventario.pdf`**: Livro Registro de Inventário no modelo P7, por grupo, com totais e numeração de folha;
- **`_dominio_saldo_estoque.xlsx` / `.csv`**: para o Importador do Domínio (abaixo);
- **`_sped_bloco_h.txt`** (se pedir `sped`): registros 0190, 0200, H005 e H010.

### Importação no Domínio

O Domínio importa o saldo pelo **Utilitários > Importação > Importador**, com os conjuntos de dados "Saldo do Estoque (Excel)" (produtos já cadastrados) ou "Cadastro e Saldo de Produtos (Excel) (3.0)" (cadastra o produto e o saldo), informando a **Data do Saldo** na guia Argumentos. A planilha tem um modelo próprio, disponível na Central de Soluções do Domínio (soluções 9498 e 4709).

**As colunas desse modelo não estão embutidas nesta skill**, porque não foi possível conferi-las contra um arquivo real. Por isso:
1. peça ao usuário a planilha modelo do Domínio (`.xlsx`) na primeira vez e passe em `--modelo-dominio`;
2. o script reconhece o cabeçalho do modelo, preenche as colunas que conhece, mostra o mapeamento e avisa quais colunas ficaram vazias. Leia esse aviso: se uma coluna vazia for obrigatória (ex.: conta contábil, tipo do item), preencha com o usuário;
3. sem o modelo, o script gera uma planilha genérica e avisa. Não a apresente como pronta para importar.

O `.csv` sai sem cabeçalho, em ANSI, para o caso de o Importador pedir CSV. Alternativa quando o modelo não estiver à mão: gerar `--formatos sped --uf SP --cod-mun 3550308` e importar em Relatórios > Informativos > Federais > SPED Fiscal, marcando "Registro de Inventário". Esse TXT serve só para a importação; não é uma EFD transmissível. Nenhuma das duas rotas foi testada dentro do Domínio: peça ao usuário para importar primeiro numa empresa de teste ou conferir o relatório de inventário depois de importar, e para avisar se algo for rejeitado.

## Passo 7 – Entregar

Entregue os arquivos e um resumo curto com:
- método, regime e critério de custo usados;
- quantidade de itens e valor total do estoque; estoque inicial, compras, CMV e CMV/vendas, quando houver;
- pendências que ficaram abertas e o efeito de cada uma (ex.: "12 itens com saldo negativo ficaram fora; somam cerca de R$ X em vendas sem entrada");
- o que o usuário precisa conferir ou fornecer (fornecedores de uso e consumo, de-para, planilha modelo);
- o `depara.csv`, para reaproveitar.

Deixe claro o grau de certeza do número. Um inventário por `contagem` é um fato medido; por `movimentacao` é um cálculo que depende de as notas estarem completas; por `alvo` é uma **estimativa**. Nos dois últimos, diga isso com todas as letras no resumo e recomende que o cliente valide e assine o inventário, já que a responsabilidade pelo estoque declarado é dele. Não ajuste quantidades ou custos só para o resultado fechar sem registrar o critério: o que foi feito precisa estar explicável numa fiscalização.
