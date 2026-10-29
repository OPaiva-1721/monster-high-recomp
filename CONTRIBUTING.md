# Contribuir / contributing

Leia o README, setup e guia do port. Contribuições pequenas e verificáveis são bem-vindas.
Please include the game/version, commit, exact reproduction, tests and limitations.
Do not upload game data, firmware, keys, saves, generated code or captures.

## Código e testes

1. Use branch/PR para uma alteração focada e o SDK fixado para aquele port.
2. Não inclua `build/`, `external/`, dados extraídos, lift ou executáveis derivados.
3. Use teste sintético quando possível; não é preciso possuir ROM para contribuir
   com ferramentas, documentação ou testes puros.
4. Rode os testes pertinentes e `git diff --check`. Informe o que não testou.
5. Preserve avisos de terceiros e documente opções experimentais.

```text
python -m unittest discover -s tools -p test_audit_publication.py -v
python -m unittest discover -s tools -p test_port.py -v
python -m unittest discover -s tools/monster_high -p test_*.py -v
```

## Relatos e desempenho

Informe edição/revisão, Windows, CPU/GPU/driver, etapa, frequência e reprodução.
Remova dados pessoais dos trechos de log. Não envie jogos, firmware, chaves ou
saves. Ausência de teste não é falha confirmada.

Compare FPS na mesma cena/câmera/save/configuração e sem jogo concorrente,
informando método/dispersão. FPS de menu não comprova combate. Não remova
geometria/efeitos/jobs para alegar ganho. Nunca encerre processos alheios.

Labels sugeridas: `needs-verification`, `bug`, `performance`, `documentation`,
`help wanted`. Reserve `good first issue` para tarefa pequena, delimitada e
com critério de verificação claro.

As contribuições autorais usam MIT. Preserve licenças/atribuições de terceiros.
