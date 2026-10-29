# Controles de PC do Naruto

Perfil Windows do Naruto, ativado pelo proprio port, sem mudar o padrao dos
outros jogos. O executavel usa `naruto-controls.ini` ao lado do EXE.

| Acao / botao PS3 | Tecla padrao |
|---|---|
| Mover / analogico esquerdo | WASD |
| Camera / analogico direito | Mouse, com captura ativada |
| Pular / confirmar (Cross) | Espaco |
| Atacar / voltar (Circle) | Mouse esquerdo |
| Shuriken (Square) | Mouse direito |
| Chakra (Triangle) | E |
| L1 / R1 | Q / R |
| L2 / R2 | Shift / Ctrl |
| Pausa / Start | Esc ou Enter |
| Select | Tab |
| Direcional dos menus | Setas |
| Capturar / soltar mouse | F1 |

Esc envia Start e nao fecha o jogo nesse perfil. Tambem libera o cursor.
Depois de fechar a pausa, F1 retoma a camera. Alt+F4 ou o X da janela fecha
o jogo. Ao trocar de janela o cursor e liberado; dialogos do mesmo processo
nao sao tratados como a janela do jogo. O clique usado para focar a janela
nao vira um ataque automaticamente.

## Personalizar

Edite o INI e reinicie o jogo. Cada movimento/botao aceita uma ou duas
teclas separadas por virgula; `NONE` desativa. Por exemplo:

```ini
[move]
forward=I
[buttons]
cross=SPACE,K
[mouse]
sensitivity=0.06
invert_y=1
capture_key=F2
```

Nomes aceitos: A..Z, 0..9, SPACE, ENTER, ESC, TAB, SHIFT, CTRL, ALT,
UP, DOWN, LEFT, RIGHT, F1..F12, MOUSE1..MOUSE5, NONE. Sensibilidade valida
entre 0.001 e 2.0; `enabled` e `invert_y` aceitam 0/1. Valores invalidos
mantem o padrao e produzem aviso. Evite usar a tecla de captura numa acao
do jogo. As setas nao movimentam o analogico; WASD nao aperta os botoes de
ataque. Diagonais mantem o mesmo raio analogico do movimento reto.

O build e a instalacao copiam o INI apenas se ainda nao existir, preservando
edicoes. `PAD_CONFIG` pode apontar outro INI. `PAD_PROFILE=legacy` recupera
o teclado anterior; `PAD_PROFILE=naruto-pc` habilita o novo em outro build
Windows D3D12. `PAD_NO_KEYBOARD=1` desliga teclado e mouse. Um controle
fisico continua disponivel: botoes sao combinados, e analogicos do teclado
ou mouse substituem o eixo do controle apenas enquanto ativos.

Prompts do jogo ainda mostram simbolos PS3; este trabalho nao altera assets
nem implementa um menu grafico de remapeamento. Mouse emula o analogico
direito, portanto continua sujeito aos limites e modos da camera do jogo.

## Implementacao e verificacao

`libs/input/pad_pc_profile.h`: tradutor puro. `pad_pc_win32.h`: INI, foco,
captura e eventos. O backend registra o HWND exato da janela do jogo.
Eventos curtos de teclado/mouse ficam pendentes ate um `cellPadGetData`
do port0 com len positivo; consultas de info nao consomem o clique. Perder
foco apaga eventos pendentes. As entradas automatizadas PAD_FILE/PAD_SCRIPT
continuam independentes para navegacao de diagnostico.

Testes: `naruto_pc_pad`, `naruto_pc_pad_win32` (Win32 simulado, nao captura
o cursor real) e `naruto_pc_config_preserved`. Asserts permanecem ativos
tambem em builds Release. Uma copia de teste com validacao somente por PID
reproduziu a captura indevida de dialogo e falhou; a versao com HWND passa.
Hooks de Escape/foco/eventos tambem compilam no backend Vulkan Windows e
em cellPad com SDL2; validacao interativa Vulkan e controle fisico pendentes.

Validacao D3D12: Esc pula abertura sem encerrar, Espaco confirma/carrega,
W movimenta Naruto, Espaco pula e mouse gira a camera na vila. F1 alterna
captura. O trecho amostra/escrita/consumo fica sob SRWLOCK; eventos novos
e consultas paralelas nao apagam entradas ainda nao entregues. Testes
concorrentes cobrem novo clique e movimento durante entrega.

Build real D3D12 e verificacoes de compilacao SDL/Vulkan passaram; 17 CTests
passaram em 15.54 s. Revisao Sol sem pendencias. Controle fisico e sessao
interativa Vulkan nao testados. Nada derivado do jogo vai para o Git.
