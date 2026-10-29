# Validação do instalador experimental

Validação local em 29/10/2026, Windows x64/D3D12. Os testes foram concentrados
no final por solicitação do usuário. Não é validação de campanha completa.

## Motor e ferramentas

- 37 testes do instalador: identidade SFO/ELF, estado e hashes, retomada,
  proteção de userdata, falta de espaço, cancelamento de processo próprio,
  lock, rede indisponível, snapshot malicioso/incompleto, ativação de revisão,
  estados da UI e fechamento de sessão própria.
- 34 testes de pipeline/auditoria por repositório.
- Atalho real executado via cmd.exe em pasta com espaços e acentos.
- SDK obtido do upstream, patch e árvore conferidos pelo lock. Saídas de PPU,
  SPU e build produzidas em destino novo; nenhum lift antigo foi copiado.
- Auditoria do histórico Git sem bloqueadores nem alertas na revisão examinada.

Nove testes adicionais das ferramentas de localização passaram. Isso não prova
layout ou revisão linguística dentro do jogo.

## Execução local

Instalação nova gerou PPU e três imagens SPU, compilou e abriu sem lifts antigos.
Criada personagem nova pelo teclado; pátio, Frankie, diálogo e objetivo Talk to
Bloodgood observados. Escada, porta e Foyer renderizados com NPCs. Após fechar e
reabrir, o slot, aparência e objetivo foram restaurados. A versão atualizada
também reabriu esse save no pátio, sem copiá-lo de outra instalação.

## Atualização e preservação

Revisão de origem atualizada para `5e68c1b52183`. O transporte HTTP
foi substituído pelos objetos exatos de um commit Git local ainda não publicado;
extração verificada, novo motor, geração, compilação e ativação foram reais.
Não se trata de teste de download de uma release publicada no GitHub.

Os 5 arquivos existentes em userdata mantiveram exatamente seus hashes
durante a atualização. Executável anterior preservado; apontamento ativo trocado
somente após conclusão. Falhas de rede/build e retomada também têm testes sintéticos.

## Pacote e limites

O empacotador usa somente fontes versionadas e bibliotecas do Python/PyInstaller;
não inclui dump, firmware, lift, jobs extraídos nem executável recompilado do jogo.
Identidade do Setup pode ser conferida com `--describe arquivo.json`; o SHA-256
acompanha cada arquivo gerado em `build/package/<commit>/dist`.

A interface chama o mesmo motor exercitado pela CLI. Abertura da janela e
mensagens de requisitos são testes de UI; não substituem os testes reais do motor.
Não houve segunda máquina Windows independente nem prova de compilação completa
em caminho acentuado. Áudio auditivo, controle físico, campanha e estabilidade
longa continuam fora desta validação. Não há promessa de FPS estável.

O runtime pode deixar threads vivas depois de fechar a janela. O launcher espera
30 segundos sem nenhuma janela visível do próprio filho já observado e encerra
somente esse processo restante; janela minimizada não dispara essa limpeza.
Não há timeout enquanto a janela do jogo permanece aberta.
