# Execução do plano de instalação

- Plano aprovado em 28/10/2026; implementação inline, MH antes do Naruto.
- Ruling: testes executados somente no final — pedido explícito mais recente do
  usuário prevalece sobre TDD e gates intermediários; custo: regressões podem
  ser descobertas juntas na validação final.
- Ruling: permitir a UI ser implementada antes da prova do pipeline — necessário
  para cumprir o pedido de fazer tudo antes de testar; não autoriza declarar
  instalação pronta ou publicar Setup sem a prova final.
- Inspeção read-only: hashes das duas edições obtidos dos dumps locais; nenhum
  jogo aberto. Perfis não contêm dados derivados além de metadados/hashes.
- Implementados: validação SFO/ELF, journal, extração de jobs, SDK fixado,
  motor CLI, retomada, isolamento de userdata, UI e atualização por snapshot.
- Pendente: testes finais, build limpo, UI/pacote, runtime, ambiente externo,
  revisão final, PRs e aprovação do pacote concreto.

- Final: 38 testes do motor e 34 das ferramentas passaram; integração real de
  instalação, atualização local e preservação de userdata documentada em INSTALL_VALIDATION.
- Final: corrigidos caminhos de shell (destino/opções/origem/root), include shim
  com espaços, ambiente de geração herdado, arquivos SDK vazios válidos e cache
  de geração por manifestos/hashes. Regressões específicas cobertas.
- Final: atualização executa o motor da nova revisão verificada, não a cópia velha;
  só confirma sucesso depois da ativação da revisão esperada.
- Final: revisão de ciclo de processo próprio pediu tratar EnumWindows desconhecido
  e falha de taskkill; ambos corrigidos e cobertos por testes.
- Ruling: limpeza somente após 30s sem janela de um filho já observado — o runtime
  não finalizava threads ao fechar; não alterar SDK nem encerrar sessão minimizada.
  Custo: fechamento de threads remanescentes é forçado e fica registrado no log.
- Ruling: transporte do ensaio de atualização usa objetos Git locais verificados —
  fontes ainda não publicadas; não declarar download de release aprovado. Custo:
  endpoint publicado deve ser conferido depois da autorização de publicação.
- Ruling: segunda máquina Windows indisponível — registrar limite e tratar pacote
  como experimental, sem simular validação externa. Custo: diferenças de ambiente
  ainda podem revelar requisitos adicionais.

- Final: proteção de origem/root contra metacaracteres reproduzida em dois testes falhando e corrigida; 38 testes passaram.
- Final: mutex Win32 entre launchers fecha a corrida entre conferir processos e abrir o jogo; teste nativo verifica bloqueio e liberação.
- Final: Ctrl+C no motor CLI encerra apenas a árvore iniciada pelo Runner; cancelamento real e regressão cobertos.

A decifragem real de EBOOT.BIN passou com RPCS3 isolado pelo próprio motor;
ELF conferido pelo hash do perfil e origem intacta. O motor copia somente
executável/dependências do RPCS3 para cache privado com portable vazio, sem
copiar nem alterar as configurações da instalação original.
