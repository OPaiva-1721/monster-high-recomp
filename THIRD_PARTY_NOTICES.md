# Componentes de terceiros

Este preview contém adaptações/patches e receitas, não árvores de dependências
ou dados dos jogos. Preserve as licenças e atribuições de cada componente.

| Componente | Uso | Licença indicada na receita/projeto |
| --- | --- | --- |
| [ps3recomp](https://github.com/sp00nznet/ps3recomp) | Runtime, lifters e templates; bases/patches nos locks por port | MIT; preservar LICENSE upstream |
| [FFmpeg](https://ffmpeg.org/) | Vídeo/áudio externo | A distribuição local era compartilhada LGPL. Confira a configuração/licença da build efetivamente usada. |
| [SDL2](https://www.libsdl.org/) | Caminhos históricos/multiplataforma | zlib |
| [glslang](https://github.com/KhronosGroup/glslang) | Caminhos históricos Vulkan | BSD-3 e avisos das partes incluídas |
| [libucontext](https://github.com/kaniini/libucontext) | Caminhos históricos Android/POSIX | ISC |

Templates/código de upstream mantêm seus termos originais. A proposta autoral
não os relicencia. Não há DLLs de FFmpeg neste pacote; um pacote binário futuro
exige revisão dos componentes que de fato o acompanhem.

Nomes dos jogos identificam compatibilidade pretendida. Jogos e seus dados não
fazem parte do código autoral disponibilizado.

## Empacotamento do Setup

PyInstaller 6.22.3: GPL-2.0 com exceção para distribuição de programas empacotados; alguns componentes Apache-2.0. Python/Tcl/Tk preservam suas licenças.
Referências: https://pyinstaller.org/en/stable/license.html e https://www.python.org/psf/license/. O empacotador não é incorporado ao jogo.
