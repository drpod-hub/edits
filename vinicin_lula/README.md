# Vinicin reage: Lula eleito — corte viral

Gera um corte vertical (1080×1920, ~61 s) a partir da live "VINICIN REAGE LULA REELEITO".

```bash
pip install pillow numpy soundfile   # ffmpeg precisa estar no PATH
python3 vinicin_lula/make_corte.py VIDEO_ORIGINAL.mp4   # -> output/vinicin_lula_corte.mp4
```

Estrutura: gancho (grito no "Breaking News") → "MINUTOS ANTES..." o desabafo
("eu não quero ganhar, quero ver vocês perder") → o "fala Bolsonaro pra tu ver" →
o anúncio do Lula e o "deu nós".

A edição fica toda na lista `PIECES` em `make_corte.py` (tempos do vídeo original,
texto da legenda, efeitos: `punch`, `shake`, `flash`, `boom`, `whoosh`, emoji).
