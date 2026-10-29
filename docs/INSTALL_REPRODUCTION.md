# Reprodução da instalação

Implementação em 28/10/2026. Testes e gameplay foram adiados para a fase final,
conforme solicitação do mantenedor; não há aprovação de instalação nesta etapa.

Inspeção do pipeline identificou dependência implícita do SDK padrão no script
auxiliar de jobs. O instalador fornece o SDK explicitamente; seu patch é
verificado por SHA-256 e árvore Git, em clone separado sem checkout inicial.

Monster High possui três imagens SPU embutidas; o pipeline já as extrai do ELF.
A bridge JobQueue executa os binários lidos do guest e não exige distribuir nem
copiar os binários locais de análise. O perfil usa o hash do ELF da edição real.

Naruto possui uma imagem SPU e quatro jobs usados no build conhecido. Os quatro
binários foram localizados integralmente dentro do ELF correspondente. Seu
perfil registra offsets/tamanhos/SHA-256 para extração na máquina do jogador;
nenhum byte de job é distribuído no perfil. A instalação deve provar geração,
registro e compilação, não apenas existência de diretórios.

Faltam resultados do ensaio final de instalação limpa e de outro ambiente.
Essas lacunas não podem ser substituídas por testes sintéticos.
