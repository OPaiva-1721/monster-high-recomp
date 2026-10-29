# Setup de desenvolvimento no Windows

Preview de fontes. O executável local do autor não é incluído. A aplicação dos
patches em cópias limpas foi conferida por equivalência de árvore Git; o build
completo em uma máquina externa ainda não foi validado.

## Dependências

Git, Python 3.12, CMake, Ninja, MSVC Build Tools/linker e Windows SDK.
O compilador local foi clang-cl do NDK 28.2.13676358. Configure o caminho do
compilador se ele não estiver no PATH; o alvo continua sendo PC, sem celular/ADB.

No setup local foi usado FFmpeg 8.1 compartilhado: headers em `external/ffmpeg/include`,
DLLs `avcodec-62.dll`, `avutil-60.dll`, `swresample-6.dll` em `external/ffmpeg/bin`.
Forneça dependências compatíveis e confira suas licenças. Não há download de jogos/firmware.

## SDK fixado por port

Na raiz, em PowerShell, escolha um jogo:

```powershell
$game = 'monster-high'
$lock = Get-Content "ports/$game/sdk.lock.json" -Raw | ConvertFrom-Json
$sdk = 'external/ps3recomp'
git clone $lock.upstream $sdk
git -C $sdk checkout --detach $lock.base
$patch = Join-Path (Get-Location) $lock.patch
git -C $sdk apply --check $patch
git -C $sdk apply $patch
```

Pare se algum comando falhar. Não reaplique num SDK com mudanças locais.
`source_revision` no lock é procedência local, não commit a buscar no upstream.
O commit público é `base`; aplique o patch correspondente ao jogo.

## Dados e configuração

O padrão é `rom/<jogo>/game/PS3_GAME` e `rom/dev_flash`. Também pode manter seus
dados em outro local. `port.ini` é exemplo público; crie um `port.local.ini`
ignorado pelo Git dentro da mesma pasta do port para substituir campos:

```ini
[port]
EBOOT_BIN = D:/meus-dados/PS3_GAME/USRDIR/EBOOT.BIN
EBOOT_ELF = D:/meus-dados/PS3_GAME/USRDIR/EBOOT.elf
VCVARS64 = C:/minha-instalacao/VC/Auxiliary/Build/vcvars64.bat

[cmake]
CMAKE_C_COMPILER = C:/meu-compilador/clang-cl.exe
CMAKE_CXX_COMPILER = C:/meu-compilador/clang-cl.exe

[env]
PS3_VFS_ROOT = D:/meus-dados
PS3_DEV_FLASH = D:/meu-firmware/dev_flash
```

A raiz VFS contém `PS3_GAME`, não é o `USRDIR`. Variáveis de ambiente de campos
`[port]` prevalecem. Saídas ficam no `build/` deste checkout. Lifts compartilhados
podem ser somente leitura. Não compartilhe HDD0/saves com outra instalação.

## Pipeline

Cada etapa é independente; não executa as anteriores automaticamente:

```powershell
python tools/port.py monster-high lift --dry-run
python tools/port.py monster-high lift
python tools/port.py monster-high lift-spu
python tools/port.py monster-high build
python tools/port.py monster-high run --interactive
```

`lift` requer seu ELF
já decifrado. `decrypt` é opcional e copia a entrada antes de invocar seu RPCS3;
configure `RPCS3` em `[port]`/ambiente e use o ELF de saída informado por ela.

`lift-spu` gera imagens SPU e processa jobs já presentes no diretório local.
Alguns jobs SPURS precisam ser coletados da sua própria execução e reliftados;
o pipeline informa quando estão ausentes. Ainda não há garantia de preparação
inteiramente automática desde o disco. Informe a etapa exata se não avançar.

`run --interactive` não tem timeout nem input automático e recusa iniciar se
outro jogo/RPCS3 estiver aberto no Windows. Feche pela janela do jogo.
`run` sem essa opção e `cap` são diagnósticos temporizados.

## Saves e controles

HDD0/dados de execução ficam no `build/`. Saves podem estar sob
`gamedata/dev_hdd0/home/00000001/savedata` no diretório de execução. Confira a
pasta e mantenha backup antes de limpar builds. Não suponha equivalência entre
saves do RPCS3 e do port. Feche o jogo antes de editar o INI.

Use o guia de controles do port. Não ative perfil/captura para medir uso normal:
o próprio diagnóstico pode introduzir pausas. Rode um jogo por vez.
