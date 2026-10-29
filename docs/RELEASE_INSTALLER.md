# Setup 0.1.0 experimental para Windows

Instalador de fontes para a edição PS3 indicada no perfil. Escolha seu dump e
as ferramentas em uma janela; o motor valida, gera e compila o jogo localmente.
Atualizações preservam userdata e mantêm a versão anterior. Não acompanha jogo,
firmware, lift nem executável recompilado.

Requer Windows x64/D3D12, Python 3.12+, Git/CMake/Ninja, ferramentas C++/Clang
do Visual Studio, FFmpeg 8.1 compartilhado e firmware próprios. Reserve 12 GiB
livres além do dump. RPCS3 é usado somente se faltar seu EBOOT.elf decifrado.

Use docs/INSTALL.md e docs/INSTALL_VALIDATION.md. O pacote é experimental:
campanha completa, áudio auditivo, controle físico e segunda máquina Windows
não foram aprovados por estes testes. A atualização foi exercitada entre
commits locais verificados; o endpoint público depende da publicação das fontes.

Distribuição prevista: Setup.exe e seu arquivo SHA-256. Os arquivos gerados
durante a instalação permanecem somente no computador do usuário.
