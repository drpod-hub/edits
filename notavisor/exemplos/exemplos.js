// Notas fictícias (ambiente de homologação, sem valor fiscal) para testar o NotaVisor.
window.EXEMPLOS = {
  nfe: `<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
<NFe><infNFe Id="NFe35261011222333000181550010000012341123456787" versao="4.00">
<ide><cUF>35</cUF><cNF>12345678</cNF><natOp>VENDA DE MERCADORIA</natOp><mod>55</mod><serie>1</serie><nNF>1234</nNF>
<dhEmi>2026-10-09T10:15:00-03:00</dhEmi><dhSaiEnt>2026-10-09T14:00:00-03:00</dhSaiEnt><tpNF>1</tpNF><idDest>1</idDest><cMunFG>3550308</cMunFG>
<tpImp>1</tpImp><tpEmis>1</tpEmis><cDV>7</cDV><tpAmb>2</tpAmb><finNFe>1</finNFe><indFinal>0</indFinal><indPres>1</indPres><procEmi>0</procEmi><verProc>1.0</verProc></ide>
<emit><CNPJ>11222333000181</CNPJ><xNome>EMPRESA EXEMPLO COMERCIO DE PECAS LTDA</xNome><xFant>EXEMPLO PECAS</xFant>
<enderEmit><xLgr>RUA DAS AMOSTRAS</xLgr><nro>100</nro><xCpl>SALA 2</xCpl><xBairro>CENTRO</xBairro><cMun>3550308</cMun><xMun>SAO PAULO</xMun><UF>SP</UF><CEP>01001000</CEP><cPais>1058</cPais><xPais>BRASIL</xPais><fone>1130000000</fone></enderEmit>
<IE>111222333444</IE><CRT>3</CRT></emit>
<dest><CNPJ>99888777000166</CNPJ><xNome>NF-E EMITIDA EM AMBIENTE DE HOMOLOGACAO - SEM VALOR FISCAL</xNome>
<enderDest><xLgr>AVENIDA DO TESTE</xLgr><nro>2500</nro><xBairro>JARDIM MODELO</xBairro><cMun>3509502</cMun><xMun>CAMPINAS</xMun><UF>SP</UF><CEP>13010000</CEP><cPais>1058</cPais><xPais>BRASIL</xPais><fone>19999990000</fone></enderDest>
<indIEDest>1</indIEDest><IE>222333444555</IE></dest>
<det nItem="1"><prod><cProd>PX-001</cProd><cEAN>SEM GTIN</cEAN><xProd>ROLAMENTO DE ESFERAS 6203 2RS</xProd><NCM>84821010</NCM><CFOP>5102</CFOP><uCom>UN</uCom><qCom>10.0000</qCom><vUnCom>18.9000000000</vUnCom><vProd>189.00</vProd><cEANTrib>SEM GTIN</cEANTrib><uTrib>UN</uTrib><qTrib>10.0000</qTrib><vUnTrib>18.9000000000</vUnTrib><indTot>1</indTot></prod>
<imposto><vTotTrib>52.40</vTotTrib><ICMS><ICMS00><orig>0</orig><CST>00</CST><modBC>3</modBC><vBC>189.00</vBC><pICMS>18.00</pICMS><vICMS>34.02</vICMS></ICMS00></ICMS>
<IPI><cEnq>999</cEnq><IPITrib><CST>50</CST><vBC>189.00</vBC><pIPI>5.00</pIPI><vIPI>9.45</vIPI></IPITrib></IPI></imposto></det>
<det nItem="2"><prod><cProd>PX-014</cProd><cEAN>SEM GTIN</cEAN><xProd>CORREIA EM V PERFIL A 42</xProd><NCM>40103100</NCM><CFOP>5102</CFOP><uCom>PC</uCom><qCom>4.0000</qCom><vUnCom>32.5000000000</vUnCom><vProd>130.00</vProd><cEANTrib>SEM GTIN</cEANTrib><uTrib>PC</uTrib><qTrib>4.0000</qTrib><vUnTrib>32.5000000000</vUnTrib><vDesc>10.00</vDesc><indTot>1</indTot></prod>
<imposto><vTotTrib>34.10</vTotTrib><ICMS><ICMS00><orig>0</orig><CST>00</CST><modBC>3</modBC><vBC>120.00</vBC><pICMS>18.00</pICMS><vICMS>21.60</vICMS></ICMS00></ICMS>
<IPI><cEnq>999</cEnq><IPITrib><CST>50</CST><vBC>120.00</vBC><pIPI>5.00</pIPI><vIPI>6.00</vIPI></IPITrib></IPI></imposto><infAdProd>LOTE 2026-09</infAdProd></det>
<det nItem="3"><prod><cProd>PX-102</cProd><cEAN>SEM GTIN</cEAN><xProd>GRAXA DE LITIO MULTIUSO 500G</xProd><NCM>34031900</NCM><CFOP>5102</CFOP><uCom>UN</uCom><qCom>2.5000</qCom><vUnCom>24.1250000000</vUnCom><vProd>60.31</vProd><cEANTrib>SEM GTIN</cEANTrib><uTrib>UN</uTrib><qTrib>2.5000</qTrib><vUnTrib>24.1250000000</vUnTrib><indTot>1</indTot></prod>
<imposto><vTotTrib>17.20</vTotTrib><ICMS><ICMS00><orig>0</orig><CST>00</CST><modBC>3</modBC><vBC>60.31</vBC><pICMS>18.00</pICMS><vICMS>10.86</vICMS></ICMS00></ICMS>
<IPI><cEnq>999</cEnq><IPITrib><CST>50</CST><vBC>60.31</vBC><pIPI>0.00</pIPI><vIPI>0.00</vIPI></IPITrib></IPI></imposto></det>
<total><ICMSTot><vBC>369.31</vBC><vICMS>66.48</vICMS><vICMSDeson>0.00</vICMSDeson><vFCP>0.00</vFCP><vBCST>0.00</vBCST><vST>0.00</vST><vFCPST>0.00</vFCPST><vFCPSTRet>0.00</vFCPSTRet>
<vProd>379.31</vProd><vFrete>25.00</vFrete><vSeg>0.00</vSeg><vDesc>10.00</vDesc><vII>0.00</vII><vIPI>15.45</vIPI><vIPIDevol>0.00</vIPIDevol><vPIS>6.09</vPIS><vCOFINS>28.07</vCOFINS><vOutro>0.00</vOutro><vNF>409.76</vNF><vTotTrib>103.70</vTotTrib></ICMSTot></total>
<transp><modFrete>0</modFrete><transporta><CNPJ>55444333000122</CNPJ><xNome>TRANSPORTADORA FICTICIA LTDA</xNome><IE>333444555666</IE><xEnder>RODOVIA DO EXEMPLO KM 10</xEnder><xMun>JUNDIAI</xMun><UF>SP</UF></transporta>
<veicTransp><placa>ABC1D23</placa><UF>SP</UF></veicTransp><vol><qVol>3</qVol><esp>CAIXA</esp><marca>EXEMPLO</marca><pesoL>12.400</pesoL><pesoB>13.100</pesoB></vol></transp>
<cobr><fat><nFat>1234</nFat><vOrig>409.76</vOrig><vDesc>0.00</vDesc><vLiq>409.76</vLiq></fat>
<dup><nDup>001</nDup><dVenc>2026-11-09</dVenc><vDup>204.88</vDup></dup><dup><nDup>002</nDup><dVenc>2026-12-09</dVenc><vDup>204.88</vDup></dup></cobr>
<pag><detPag><indPag>1</indPag><tPag>15</tPag><vPag>409.76</vPag></detPag></pag>
<infAdic><infCpl>DOCUMENTO DE EXEMPLO GERADO PARA TESTES. PEDIDO DO CLIENTE: 4581. VALOR APROXIMADO DOS TRIBUTOS: R$ 103,70 (27,34%).</infCpl></infAdic>
</infNFe></NFe>
<protNFe versao="4.00"><infProt><tpAmb>2</tpAmb><verAplic>SP_NFE_PL009</verAplic><chNFe>35261011222333000181550010000012341123456787</chNFe><dhRecbto>2026-10-09T10:15:42-03:00</dhRecbto><nProt>135260000012345</nProt><cStat>100</cStat><xMotivo>Autorizado o uso da NF-e</xMotivo></infProt></protNFe>
</nfeProc>`,

  nfce: `<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
<NFe><infNFe Id="NFe35261011222333000181650010000005671876543216" versao="4.00">
<ide><cUF>35</cUF><cNF>87654321</cNF><natOp>VENDA AO CONSUMIDOR</natOp><mod>65</mod><serie>1</serie><nNF>567</nNF>
<dhEmi>2026-10-09T18:42:10-03:00</dhEmi><tpNF>1</tpNF><idDest>1</idDest><cMunFG>3550308</cMunFG><tpImp>4</tpImp><tpEmis>1</tpEmis><cDV>6</cDV><tpAmb>2</tpAmb><finNFe>1</finNFe><indFinal>1</indFinal><indPres>1</indPres><procEmi>0</procEmi><verProc>1.0</verProc></ide>
<emit><CNPJ>11222333000181</CNPJ><xNome>EMPRESA EXEMPLO COMERCIO DE PECAS LTDA</xNome>
<enderEmit><xLgr>RUA DAS AMOSTRAS</xLgr><nro>100</nro><xBairro>CENTRO</xBairro><cMun>3550308</cMun><xMun>SAO PAULO</xMun><UF>SP</UF><CEP>01001000</CEP></enderEmit><IE>111222333444</IE><CRT>1</CRT></emit>
<dest><CPF>12345678909</CPF></dest>
<det nItem="1"><prod><cProd>789000000001</cProd><cEAN>SEM GTIN</cEAN><xProd>CAFE TORRADO 500G</xProd><NCM>09012100</NCM><CFOP>5102</CFOP><uCom>UN</uCom><qCom>2.0000</qCom><vUnCom>21.9000000000</vUnCom><vProd>43.80</vProd><indTot>1</indTot></prod>
<imposto><vTotTrib>9.20</vTotTrib><ICMS><ICMSSN102><orig>0</orig><CSOSN>102</CSOSN></ICMSSN102></ICMS></imposto></det>
<det nItem="2"><prod><cProd>789000000002</cProd><cEAN>SEM GTIN</cEAN><xProd>PAO DE FORMA INTEGRAL</xProd><NCM>19059090</NCM><CFOP>5102</CFOP><uCom>UN</uCom><qCom>1.0000</qCom><vUnCom>9.4900000000</vUnCom><vProd>9.49</vProd><indTot>1</indTot></prod>
<imposto><vTotTrib>2.10</vTotTrib><ICMS><ICMSSN102><orig>0</orig><CSOSN>102</CSOSN></ICMSSN102></ICMS></imposto></det>
<det nItem="3"><prod><cProd>789000000003</cProd><cEAN>SEM GTIN</cEAN><xProd>BANANA PRATA KG</xProd><NCM>08039000</NCM><CFOP>5102</CFOP><uCom>KG</uCom><qCom>1.2350</qCom><vUnCom>6.9900000000</vUnCom><vProd>8.63</vProd><indTot>1</indTot></prod>
<imposto><vTotTrib>0.00</vTotTrib><ICMS><ICMSSN102><orig>0</orig><CSOSN>102</CSOSN></ICMSSN102></ICMS></imposto></det>
<total><ICMSTot><vBC>0.00</vBC><vICMS>0.00</vICMS><vBCST>0.00</vBCST><vST>0.00</vST><vProd>61.92</vProd><vFrete>0.00</vFrete><vSeg>0.00</vSeg><vDesc>1.92</vDesc><vII>0.00</vII><vIPI>0.00</vIPI><vPIS>0.00</vPIS><vCOFINS>0.00</vCOFINS><vOutro>0.00</vOutro><vNF>60.00</vNF><vTotTrib>11.30</vTotTrib></ICMSTot></total>
<transp><modFrete>9</modFrete></transp>
<pag><detPag><tPag>01</tPag><vPag>50.00</vPag></detPag><detPag><tPag>17</tPag><vPag>20.00</vPag></detPag><vTroco>10.00</vTroco></pag>
</infNFe>
<infNFeSupl><qrCode>https://www.homologacao.nfce.fazenda.sp.gov.br/qrcode?p=35261011222333000181650010000005671876543216|2|2|1|0000000000000000000000000000000000000000</qrCode><urlChave>https://www.homologacao.nfce.fazenda.sp.gov.br/consulta</urlChave></infNFeSupl>
</NFe>
<protNFe versao="4.00"><infProt><tpAmb>2</tpAmb><chNFe>35261011222333000181650010000005671876543216</chNFe><dhRecbto>2026-10-09T18:42:13-03:00</dhRecbto><nProt>135260000098765</nProt><cStat>100</cStat><xMotivo>Autorizado o uso da NF-e</xMotivo></infProt></protNFe>
</nfeProc>`,
};
