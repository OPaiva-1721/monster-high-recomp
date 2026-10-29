# Monster High: New Ghoul in School — port experimental para PC

Recompilação experimental para **Windows x64/D3D12**, usando ps3recomp.
Preview de fontes e ferramentas, aberto a contribuições. Não é um jogo pronto.

Experimental Windows/D3D12 recompilation port. Sources and tools only;
bring your own compatible game data. Full gameplay and external setup remain unverified.

- [Setup e build](docs/PC_SETUP.md)
- [Guia do port](ports/monster-high/README.md)
- [Estado e pendências](docs/STATUS_PC.md)
- [Controles](docs/PC_CONTROLS.md)
- [Como contribuir](CONTRIBUTING.md)

Você fornece seus dados/firmware e gera lift e executável localmente.
Não inclui ROM, ISO, EBOOT, firmware, chaves, código gerado, executáveis,
saves, capturas ou arquivos de tradução do jogo. Não envie esses arquivos em issues/PRs.

SDK e patch fixados em `ports/monster-high/sdk.lock.json`. O setup é voltado a
desenvolvedores e ainda pode exigir coleta local de jobs SPURS.
Os testes automáticos usam fixtures sintéticas; não comprovam gameplay.

Contribuições autorais sob [MIT](LICENSE); [avisos de terceiros](THIRD_PARTY_NOTICES.md).
Nomes e marcas pertencem aos respectivos titulares. Projeto independente de fãs.
