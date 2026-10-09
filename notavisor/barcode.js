// Code 128 (sets B e C) em SVG — usado no código de barras da chave de acesso.
(function () {
  const PATTERNS = [
    '212222', '222122', '222221', '121223', '121322', '131222', '122213', '122312', '132212', '221213',
    '221312', '231212', '112232', '122132', '122231', '113222', '123122', '123221', '223211', '221132',
    '221231', '213212', '223112', '312131', '311222', '321122', '321221', '312212', '322112', '322211',
    '212123', '212321', '232121', '111323', '131123', '131321', '112313', '132113', '132311', '211313',
    '231113', '231311', '112133', '112331', '132131', '113123', '113321', '133121', '313121', '211331',
    '231131', '213113', '213311', '213131', '311123', '311321', '331121', '312113', '312311', '332111',
    '314111', '221411', '431111', '111224', '111422', '121124', '121421', '141122', '141221', '112214',
    '112412', '122114', '122411', '142112', '142211', '241211', '221114', '413111', '241112', '134111',
    '111242', '121142', '121241', '114212', '124112', '124211', '411212', '421112', '421211', '212141',
    '214121', '412121', '111143', '111341', '131141', '114113', '114311', '411113', '411311', '113141',
    '114131', '311141', '411131', '211412', '211214', '211232', '2331112',
  ];
  const START_B = 104, START_C = 105, STOP = 106;

  function codes(data) {
    let out;
    if (/^\d+$/.test(data) && data.length % 2 === 0) {
      out = [START_C];
      for (let i = 0; i < data.length; i += 2) out.push(parseInt(data.substr(i, 2), 10));
    } else {
      out = [START_B];
      for (const ch of data) {
        const c = ch.charCodeAt(0) - 32;
        if (c < 0 || c > 95) throw new Error('Caractere inválido para Code 128: ' + ch);
        out.push(c);
      }
    }
    let sum = out[0];
    for (let i = 1; i < out.length; i++) sum += out[i] * i;
    out.push(sum % 103, STOP);
    return out;
  }

  // Retorna um <svg> com as barras; a largura se ajusta ao contêiner.
  function code128Svg(data, height = 50) {
    const widths = codes(data).map(c => PATTERNS[c]).join('');
    const quiet = 10;
    let x = quiet, rects = '';
    for (let i = 0; i < widths.length; i++) {
      const w = +widths[i];
      if (i % 2 === 0) rects += `<rect x="${x}" y="0" width="${w}" height="${height}"/>`;
      x += w;
    }
    const total = x + quiet;
    return `<svg class="barcode" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${total} ${height}" preserveAspectRatio="none" shape-rendering="crispEdges" role="img" aria-label="Código de barras ${data}"><g fill="#000">${rects}</g></svg>`;
  }

  window.Code128 = { codes, svg: code128Svg, PATTERNS };
})();
