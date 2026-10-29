# Monster High: New Ghoul in School — port experimental para PC

Recompilação experimental para **Windows x64/D3D12**, usando ps3recomp.
Aberto a contribuições; campanha completa e estabilidade geral continuam em desenvolvimento.

## Instalar no Windows

Baixe o [Setup experimental 0.1.0](https://github.com/OPaiva-1721/monster-high-recomp/releases/tag/v0.1.0)
e confira o SHA-256 que acompanha o arquivo. O Setup recompila **sua própria cópia
PS3 BLES02199 01.00** localmente; não baixa nem inclui o jogo ou firmware.

Requer Python 3.12+, Git/CMake/Ninja, Visual Studio Build Tools com C++/Clang,
FFmpeg 8.1 compartilhado e dev_flash próprios. Reserve 12 GiB livres além do dump.
Escolha a pasta contendo PS3_GAME e um destino novo; após concluir, use Jogar.cmd.

- [Guia do instalador e requisitos](docs/INSTALL.md)
- [Validação e limites conhecidos](docs/INSTALL_VALIDATION.md)
- [Build manual](docs/PC_SETUP.md)
- [Estado do port](docs/STATUS_PC.md)
- [Controles](docs/PC_CONTROLS.md)
- [Como contribuir](CONTRIBUTING.md)

Instalação limpa, execução inicial, atualização entre commits locais e recarga de
saves foram verificadas neste PC. Segunda máquina Windows, áudio auditivo,
controle físico e campanha completa ainda não foram validados. Veja o relatório.

O SDK/patch é fixado em `ports/monster-high/sdk.lock.json`. PPU/SPU/jobs necessários são
gerados a partir do ELF do usuário; não é preciso baixar jobs coletados de terceiros.
Saves/configurações permanecem em userdata durante atualizações.

Experimental Windows/D3D12 source installer. Bring your own compatible PS3 game
data, firmware and build tools. Full campaign and independent-PC validation remain pending.

Não inclui ROM, ISO, EBOOT, firmware, chaves, lift, executável recompilado do jogo,
saves, capturas ou arquivos de tradução derivados. Não envie esses arquivos em issues/PRs.
O Setup inclui somente motor/fontes e dependências do Python/PyInstaller.

Contribuições autorais sob [MIT](LICENSE); [avisos de terceiros](THIRD_PARTY_NOTICES.md).
Nomes e marcas pertencem aos respectivos titulares. Projeto independente de fãs.
