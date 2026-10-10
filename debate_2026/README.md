# Debate presidencial 2026: corte "resenha"

Corte vertical (1080×1920, ~66 s) do resumo da BBC News Brasil sobre o primeiro debate de 2026 na Band, aquele em que Lula e Flávio Bolsonaro não foram.

```bash
pip install pillow numpy soundfile   # ffmpeg precisa estar no PATH
python3 debate_2026/make_resenha.py VIDEO_ORIGINAL.mp4   # -> output/debate_2026_resenha.mp4
```

Recursos: legendas palavra por palavra na cor de cada candidato, letreiros com apelido, rótulos "ENQUANTO ISSO...", congelamentos com piada e som de disco arranhando, grilos na cadeira vazia, filtro zen pro Cury e vinheta vermelha pro Renan.
Os efeitos sonoros são sintetizados no próprio script. Tudo é editável na lista `PIECES`.
