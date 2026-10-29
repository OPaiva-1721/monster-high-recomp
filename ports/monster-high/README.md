# Monster High no Windows — experimental

Edição usada: **BLES02199 01.00**, sem garantia para outras regiões/atualizações.
Veja o [setup](../../docs/PC_SETUP.md) e o [status](../../docs/STATUS_PC.md).
Você fornece seus dados/firmware e gera lift/executável localmente.

O SDK está fixado em `sdk.lock.json`. O perfil inclui:

- `MONSTER_HIGH_JOB_QUEUE=1`: bridge específica e experimental para os jobs
  observados, não uma implementação geral de SPURS JobQueue.
- `RSX_FP_USED_TEX=1`, `RSX_TRIS_UNIQUE=1`, `RSX_INDEX_BATCH=1`: opções testadas
  neste port, não promessas para outros jogos.
- `SYNC_QUEUE_SLEEP=0`, `USLEEP_POLITE=0`, `PERF=0`: hipóteses antigas e
  instrumentação não devem ser tratadas como otimização padrão.

O perfil `naruto-pc` do runtime é reutilizado. Veja `monster-high-controls.ini`
e [controles de PC](../../docs/PC_CONTROLS.md). Prompts podem continuar com
botões PS3. Controle físico não foi validado integralmente nesta preparação.

As ferramentas em `tools/monster_high/` exportam/reconstroem as tabelas observadas
da sua cópia. Use cópia separada e preserve o original. Não envie catálogo
extraído, HNK ou save ao GitHub. Testes sintéticos, sem jogo:

```text
python -m unittest discover -s tools/monster_high -p test_*.py -v
```

Offsets, IDs, heaps e tokens são verificados. Isso não garante layout/glifos
nem qualidade de tradução no jogo. A beta PT-BR local não acompanha este preview.
