# Instalação experimental de PC

O Setup é experimental. Não indica campanha completa, áudio ou controle
físico totalmente aprovados. Os dados do jogo e firmware não acompanham o download.

## Requisitos

Windows x64 com D3D12; Python 3.12+, Git, CMake e Ninja no PATH; Visual Studio
Build Tools com workload C++ e Clang para Windows. FFmpeg 8.1 compartilhado com
`bin/avcodec-62.dll`, `bin/avutil-60.dll`, `bin/swresample-6.dll` e headers em
`include`. Seu firmware instalado fornece a pasta `dev_flash`.

O Setup informa requisitos ausentes e permite selecionar ferramentas que não
encontrar. Não instala software nem altera o sistema por conta própria.
Reserve inicialmente 12 GiB livres para a geração/build, além do dump original;
o valor é um limite preventivo, não medição final do tamanho instalado.

## Como instalar

1. Execute o Setup deste repositório.
2. Escolha sua pasta contendo `PS3_GAME` e um destino novo separado.
3. Informe as dependências solicitadas. Caso tenha `EBOOT.elf` já decifrado,
   pode selecioná-lo; caso contrário selecione RPCS3 para decifrar uma cópia.
4. Clique **Instalar / retomar**. As etapas verificam edição/ELF, SDK, geração
   PPU/SPU/jobs e compilação. Acompanhe o estado; o log fica em `.installer/install.log`.
5. Use **Jogar** ou `Jogar.cmd` no destino após sucesso.

Não mova nem apague o dump ou firmware: o jogo instalado continua lendo essas
pastas originais. O instalador não modifica seus arquivos. ISO não é entrada
suportada nesta versão; extraia sua própria cópia previamente.

## Retomada, atualização e dados

Use o mesmo destino e as mesmas opções para retomar. Saídas verificadas são
reutilizadas; saída corrompida invalida a etapa e as seguintes. Cancelar encerra
somente o processo iniciado por esta instalação. Depois de encerramento forçado,
confira que o instalador não está mais rodando antes de remover exclusivamente
`.installer/install.lock`, se necessário.

`Atualizar.cmd` ou **Atualizar instalação** busca um commit do mesmo repositório,
confere o snapshot e prepara uma nova pasta de aplicação. A instalação anterior
permanece; o apontamento ativo muda somente depois do build bem-sucedido.
Se a rede/build falhar, continue usando a versão anterior.

Saves e configurações ficam em `userdata/`; não são sobrescritos ao atualizar.
Arquivos do runtime que usam caminhos relativos também têm `userdata/` como
diretório de trabalho. Faça backup dessa pasta antes de limpar instalações.
Sem instalação simultânea nem jogo/RPCS3 concorrente.

## Desenvolvedores

```text
python installer/install.py doctor
python installer/install.py install --source D:/dump --dest D:/port --firmware D:/RPCS3/dev_flash --ffmpeg D:/ffmpeg --compiler D:/LLVM/bin/clang-cl.exe --vcvars "C:/Visual Studio/VC/Auxiliary/Build/vcvars64.bat"
python installer/install.py launch --dest D:/port
python installer/install.py update --dest D:/port
python -m unittest discover -s installer -p test_*.py -v
```

`installer/package.ps1` cria ambiente privado de empacotamento e gera somente
Setup/fontes publicáveis, com SHA-256. Exige fontes commitadas. Não empacota o
executável do jogo, lift, dump, jobs extraídos, saves ou firmware.


## Fechamento da janela

Feche normalmente pelo X ou Alt+F4. Se o runtime deixar um processo sem janela,
o launcher aguarda 30 segundos e limpa apenas seu próprio filho. Minimizar não
encerra o jogo. Saves e configurações permanecem em userdata.
