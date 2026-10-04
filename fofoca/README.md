# Fofoca / Drama da Internet: gerador de shorts

Gera um vídeo vertical 1080×1920 no formato dos shorts de "drama da internet" (estilo Laestro): um narrador conta a história em frases curtas, **cada frase corta para uma imagem nova** (meme, clipe, print) e uma **legenda laranja aparece de 2 a 3 palavras por vez**.

```bash
pip install pillow edge-tts             # ffmpeg precisa estar no PATH
python3 fofoca/make_story.py            # usa fofoca/roteiro.json -> output/fofoca_ep01.mp4
python3 fofoca/make_story.py meu.json   # outro roteiro
```

Você pode renderizar antes de ter qualquer mídia. Cada arquivo que faltar vira um card cinza escrito **COLOQUE A MÍDIA** com o caminho esperado, então dá para conferir o ritmo do roteiro primeiro e juntar os memes depois.

## O que o formato faz (medido no vídeo de referência)

| Elemento | Na referência | No gerador |
|---|---|---|
| Duração | 100 s (passa de 1 min por causa da monetização) | avisa quando o vídeo tem menos de 61 s |
| Cortes | ~36 em 100 s, um a cada 1–3 s | um corte por `beat` (frase) |
| Legenda | laranja `#FFA500`, contorno escuro, brilho laranja, 2–3 palavras | `caption` (cor, brilho, tamanho, `max_words`) |
| Visual "full" | meme ou clipe em tela cheia, legenda no meio | `"mode": "full"` (padrão); imagem parada ganha zoom lento |
| Visual "card" | fundo cinza `#969696`, foto inclinada com sombra que "pula" na tela, legenda em cima | `"mode": "card"` |
| Sticker | barata no canto durante o gancho | `"sticker": {"path", "x", "y", "w"}` |
| CTA | balão "aprenda a criar vídeos… link da bio" | `"cta": {"text", "start", "end"}` |
| Som | narração alta e clara, efeitos pontuais | `voice`, `music` (baixinha), `sfx` por beat (vine boom, scratch) |

## Roteiro (`roteiro.json`)

```jsonc
{
  "output": "output/fofoca_ep01.mp4",
  "handle": "@seuperfil",
  "voice": {"engine": "edge", "name": "pt-BR-AntonioNeural", "rate": "+12%"},
  "music": "assets/fofoca/musica_suspense.mp3", "music_volume": 0.10,
  "cta": {"text": "segue pra parte 2", "start": 30, "end": 34},
  "beats": [
    {"text": "O cara que pediu a namorada em casamento no meio do churrasco",
     "media": "assets/fofoca/hook.mp4", "start": 0,
     "sticker": {"path": "assets/fofoca/barata.png", "x": 0.15, "y": 0.68, "w": 150}},
    {"text": "e foi recusado na frente de quarenta pessoas.",
     "media": "assets/fofoca/meme_choque.mp4", "sfx": "assets/fofoca/vine_boom.mp3"},
    {"text": "Pois é gente, já faz alguns dias", "media": "assets/fofoca/print.png", "mode": "card"}
  ]
}
```

Campos de cada beat:

- `text`: o que o narrador fala, que também vira a legenda.
- `media`: clipe (`.mp4/.mov/.webm/.gif`) ou imagem.
- `mode`: `full` ou `card`.
- `start`: segundo do clipe onde o trecho começa.
- `zoom`: aproxima a imagem.
- `push`: força do zoom lento em imagens (padrão `0.10`).
- `pause`: silêncio depois da frase, para criar suspense.
- `sfx`: efeito sonoro no corte (volume em `sfx_volume`).
- `sticker`: imagem pequena por cima.
- `tilt`: inclinação do card.
- `caption_y`: altura da legenda, de 0 a 1.

### Voz

| `engine` | Uso |
|---|---|
| `edge` | voz neural da Microsoft (grátis, precisa de internet). Vozes pt-BR: `pt-BR-AntonioNeural`, `pt-BR-FranciscaNeural`, `pt-BR-ThalitaMultilingualNeural` |
| `file` | **sua própria voz** gravada (`"file": "assets/fofoca/voz.m4a"`). Coloque `"at": segundos` em cada beat para sincronizar; sem isso, o tempo é dividido pelo tamanho do texto |
| `espeak` | voz robótica offline, só para prévia |
| `none` | sem som; a duração é estimada pelo texto |

**Grave com a sua voz assim que puder.** Voz própria deixa o conteúdo mais "original" para o algoritmo e para a monetização, e cria identidade de canal. A TTS serve para começar e para testar roteiros.

As mídias ficam em `assets/fofoca/`. O `.gitignore` já ignora vídeo, áudio e imagem, então nada disso vai para o git.

---

## Guia para views e monetização

### 1. A estrutura que prende (copie o ritmo, não a história)

1. **Gancho em até 2 s.** Comece com o rótulo absurdo do personagem, nunca com "oi gente": *"O streamer que é alérgico a opiniões diferentes da dele"*, *"O cara que foi recusado na frente de 40 pessoas"*. O gancho já é a manchete.
2. **"Pois é gente, já faz alguns dias…"** dá contexto rápido e confirma que é uma história real em andamento.
3. **"E se você não viu, relaxa que eu te conto"** segura quem chegou sem contexto.
4. **Escalada:** cada 3–4 frases precisam de uma virada ("detalhe:", "só que", "e o pior"). Pausa de 0.3–0.4 s antes da revelação, com efeito sonoro no corte.
5. **Reviravolta final** perto de 50–60 s, para a pessoa assistir até o fim e passar de 1 minuto.
6. **Pergunta + parte 2:** *"E você, aceitaria?"* gera comentários. *"Segue pra parte 2"* gera seguidores. Divida histórias longas em partes.

Regras de edição que o gerador já aplica: corte a cada frase, legenda curta no centro, nada parado por mais de ~3 s. O que fica com você: **meme de reação certo na frase certa** (choque, Coringa, cachorro sério, macaco brigando). É isso que faz rir e compartilhar.

### 2. Escolha de pauta

- Drama de criadores ou streamers que **já está em alta** (veja os comentários do TikTok/X, o Twitter BR e os "Em alta" do YouTube). Chegue em 24–72 h.
- Histórias "inacreditáveis" do cotidiano (casamento, churrasco, condomínio, iFood, vizinho), que funcionam com qualquer público.
- Faça **série com o mesmo formato**. Repetição de formato cria público fiel.

### 3. Monetização (confira sempre os requisitos atuais de cada plataforma)

- **TikTok (Programa de Recompensas para Criadores):** só paga vídeos com **mais de 1 minuto** e conteúdo original. É por isso que a referência tem 100 s. Mire em 65–100 s.
- **YouTube Shorts (YPP):** mesmo vídeo, receita de anúncios dividida. Shorts podem ter até 3 min.
- **Kwai e Instagram Reels:** poste também, para alcance e perfil.
- **Link na bio** (curso, mentoria, afiliado): a referência monetiza assim, com o balão "aprenda a criar vídeos curtos comigo". Use `cta`.

### 4. O que derruba o canal (evite)

- **Inventar ou exagerar acusação sobre pessoa real** é difamação: processo e strike. Conte só o que tem fonte (print, vídeo, post) e mostre a fonte num card. O `roteiro.json` de exemplo é uma **história fictícia** só para demonstrar o formato.
- **Clipe longo de terceiros sem comentário** gera conteúdo "não original", que fica sem monetização ou toma copyright. Use trechos curtos (2–4 s) que **ilustram sua narração**. Esse é o formato.
- **Música com direitos autorais** como fundo: use a biblioteca de áudio da própria plataforma ou música livre.
- **Reupload do vídeo de outra pessoa** é proibido. Inspire-se no formato e conte a história com seu roteiro e sua edição.

### 5. Rotina

- 1–2 vídeos por dia, sempre no mesmo formato, por 30 dias antes de avaliar.
- Olhe a **retenção nos 3 primeiros segundos** e o **% que assiste até o fim**. Se cair no começo, troque o gancho. Se cair no meio, corte frases mortas.
- A legenda do post deve repetir o gancho e ter 3–5 hashtags do nicho (#fofoca #treta #internet #polêmica).
