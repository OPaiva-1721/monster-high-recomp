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
