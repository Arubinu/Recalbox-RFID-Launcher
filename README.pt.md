# 🎮 Recalbox RFID Launcher

[English](README.md) · [Français](README.fr.md) · [Deutsch](README.de.md) · [Español](README.es.md) · [Italiano](README.it.md) · **Português**

**Um tag, um jogo.** Coloque um tag RFID num leitor ligado ao seu Recalbox: o jogo associado arranca, como um
cartucho. Tudo se configura a partir de uma única página web aberta no computador, sem instalar nada nele e sem linha
de comandos.
A mesma página também abre num telemóvel, servida pelo próprio Recalbox.

## 💡 A ideia

O projeto nasceu de uma imagem simples: uma **ranhura recortada na caixa da consola**, com o leitor escondido logo
atrás, onde se **inserem cartões como se fossem cartuchos de jogo**. Introduz-se um cartão e o jogo arranca; com a
definição **«Sair do jogo quando o tag é retirado»**, tirar o cartão volta ao menu do Recalbox, tal como ao retirar
um cartucho. Cada cartão pode levar a ilustração do seu jogo: uma prateleira de «cartuchos» que qualquer pessoa pode
usar, crianças incluídas, sem nunca passar pelos menus.

## ✨ Funcionalidades

- 🏷️ **Um tag = um jogo**: o jogo arranca exatamente como a partir do menu do Recalbox (ecrã de carregamento,
  gravações, conquistas)
- 🔘 **Associação em dois segundos**: posicione-se num jogo no Recalbox, prima o botão da caixa (ou clique na
  página), coloque o tag
- 🧭 **Instalação guiada**: esquema de ligação, cópia para o Recalbox, instalação a partir do menu do Recalbox 10
  **sem reiniciar**, e autorização com o botão da caixa
- 🔐 **Sem palavra-passe**: um computador é autorizado mantendo o botão da caixa premido durante 3 segundos
- 🩺 **Verificação do hardware** em linguagem simples, teste do leitor e **ajuste automático do leitor**
- 🔄 **Atualizações com um clique** a partir da página; os tags e as definições são sempre mantidos
- 🌍 **6 idiomas** (inglês, francês, alemão, espanhol, italiano, português), temas claro e escuro
- 🧩 **Sem dependências**: apenas o Python 3 já incluído no Recalbox, sem pacotes nem alterações ao sistema
- 🖨️ **Cartões para imprimir**: a imagem do jogo, o logótipo e as cores da sua consola, sete modelos, cada elemento
  pode ser movido e rodado; dez cartões por folha A4
- 📱 **Também no telemóvel**: o Recalbox serve a página ele próprio (código QR); procure um jogo e associe um tag sem
  a TV
- 🎲 **Cartões especiais**: jogo ao acaso, tempo bónus, sair do jogo, desligar
- ⏱️ **Tempo de jogo**: um limite por tag ou para todos, avisos antes do fim, cartões bónus com quota
- 💡 **Luz de estado e mensagens no ecrã**: um LED RGB ou LED programáveis, mensagens no ecrã do jogo

## 🧰 O que é preciso

| Material | Detalhe |
| --- | --- |
| Recalbox | **versão 9 ou mais recente** (recomenda-se o Recalbox 10: instalação sem reiniciar) |
| Raspberry Pi | 3, 4 ou Zero 2, a arrancar no Recalbox |
| Leitor RFID **MFRC522** | módulo «RC522», por exemplo o nf-SL001 (**apenas 3,3 V**) |
| Tags / porta-chaves | 13,56 MHz ISO 14443-A (MIFARE Classic, Ultralight…). Os tags de 125 kHz não funcionam |
| Um botão de pressão | qualquer botão de contacto momentâneo, sem resistência |
| Fios Dupont | 7 (6 para o leitor, mais 1 para o botão) |
| Luz de estado (opcional) | um módulo LED RGB ou LED programáveis WS2812: ver [docs/WIRING.md](docs/WIRING.md) |

> ⚠️ O RC522 funciona **apenas com 3,3 V**. Nunca o ligue ao pino de 5 V do Raspberry Pi: ficaria destruído.

## 🔌 Ligação

![Ligação do leitor RC522 e do botão](docs/wiring.svg)

| RC522 | Raspberry Pi (GPIO BCM) | Pino físico |
| --- | --- | --- |
| SDA | GPIO8 (CE0) | 24 |
| SCK | GPIO11 (SCLK) | 23 |
| MOSI | GPIO10 (MOSI) | 19 |
| MISO | GPIO9 (MISO) | 21 |
| RST | GPIO25 | 22 |
| GND | GND | 6 |
| 3.3V | 3V3 | 1 |
| **Botão** | GPIO17 e GND | 11 e 9 |

O programa ativa o pull-up interno do Raspberry Pi: sem resistência. Detalhes: [docs/WIRING.md](docs/WIRING.md)
(em inglês).

## 🚀 Instalação

### O mais simples: a página

1. **Transfira** `recalbox-rfid-installer.html` da [versão mais recente](../../releases/latest) (ou use
   `dist/recalbox-rfid-installer.html` deste repositório) e abra-o com o **Edge ou o Chrome**.
2. Escolha **«Instalar pela primeira vez»** e siga os quatro passos:
   1. **Ligar**: o esquema aparece no ecrã.
   2. **Copiar**: clique em «Escolher a pasta do Recalbox»; a página copia o endereço, cole-o na janela (Ctrl+V,
      Enter) e confirme. A página escreve tudo na partilha do Recalbox.
   3. **Executar**: no **Recalbox 10**, com o comando, `START` › Definições avançadas › Scripts do utilizador ›
      **Install-RFID-reader**. No **Recalbox 9**, reinicie o Recalbox. A página espera e avança sozinha; o Recalbox
      pode reiniciar uma vez sozinho para ativar o leitor.
   4. **Autorizar**: mantenha o botão da caixa premido durante 3 segundos. Abre-se a gestão dos tags.

> **Versão online**: <https://arubinu.github.io/Recalbox-RFID-Launcher/> permite fazer os passos 1 e 2. Os
> navegadores proíbem uma página `https://` de falar com um dispositivo da sua rede: a página online propõe
> transferir-se para o resto, e a página guardada no computador faz tudo.

### Se o Windows não abrir `\\RECALBOX\share`

- **O Windows propõe «Diagnosticar»**: a sua ligação está numa rede *Pública*, que esconde os dispositivos da sua
  rede. Definições › Rede e Internet › Wi-Fi ou Ethernet › a sua rede › Tipo de perfil de rede › **Privada**. Também
  pode escrever o endereço IP do Recalbox (`\\192.168.1.20\share`, visível em START › Definições de rede).
- **O Windows pede uma palavra-passe, ou nada funciona**: no passo 2, use **«Transferir o instalador do Windows»**.
  Este pequeno ficheiro `.cmd` encontra o Recalbox, liga-se à partilha, copia tudo e volta a abrir a página no
  passo 3.

### Outros métodos

- **À mão**: copie a pasta `recalbox-rfid` para `\\RECALBOX\share`, copie
  `recalbox-rfid\bootstrap\recalbox-rfid-agent(permanent).py3` para `userscripts\` e, no Recalbox 10, o conteúdo de
  `recalbox-rfid\bootstrap\manual` para `userscripts\manual\`. Depois reinicie (ou execute *Install-RFID-reader*).
- **Por SSH**: `ssh root@recalbox.local "sh /recalbox/share/recalbox-rfid/install.sh --start"` (palavra-passe
  predefinida `recalboxroot`).

Guia passo a passo: [docs/INSTALLATION.md](docs/INSTALLATION.md) (em inglês).

## 🎯 No dia a dia

- **Associar um tag**: no Recalbox, posicione-se num jogo da lista (sem o iniciar). Na página, clique em **«Associar
  um tag a este jogo»** (ou prima brevemente o botão da caixa) e coloque o tag nos 10 segundos seguintes. Dois bips
  confirmam.
- **Iniciar um jogo**: coloque o tag. O ecrã de carregamento do jogo é a confirmação visual.
- **Apagar um tag**: na página, o ícone de caixote do lixo ao lado, ou **«Apagar colocando o tag»**.
- **Guardar os seus tags**: «Guardar a lista» cria um ficheiro CSV (abre no Excel ou no LibreOffice); «Restaurar uma
  lista» volta a carregá-lo.

| Som | Significado |
| --- | --- |
| 1 bip agudo | modo de associação ativo |
| 2 bips ascendentes | tag associado |
| 1 bip médio | tag reconhecido sem ação (`action = none`) |
| nenhum som | um jogo arranca: o ecrã de carregamento basta |
| 2 bips graves | modo de apagar ativo |
| 2 bips graves descendentes | tag desconhecido ou ação recusada |
| 3 bips descendentes | tempo esgotado (10 s para colocar o tag) |

## 🖨️ Cartões, cartões especiais e tempo de jogo

- **Procurar um jogo** (separador Tags): escreva algumas letras e associe um tag ao jogo, sem a TV. Prático num
  telemóvel: abra `http://recalbox.local:8765/` (ou leia o código QR do botão do telemóvel no cabeçalho).
- **Imprimir os cartões** (separador Cartões): escolha um jogo e um modelo, horizontal ou vertical; toque num elemento
  do cartão para o mover, aumentar ou rodar; uma faixa amarela mostra a parte que fica fora da ranhura. Guarde o
  esquema como modelo, adicione os cartões à folha e imprima a 100 % (dez cartões por folha A4).
- **Cartões portáteis**: lápis de um tag › «Escrever o jogo no tag» guarda o jogo no próprio tag; funciona
  então em qualquer Recalbox que tenha o jogo (tags MIFARE Classic, Ultralight, NTAG).
- **Cartões especiais** (separador Tags): jogo ao acaso, tempo bónus, sair do jogo, desligar o Recalbox.
- **Tempo de jogo**: Definições › Tempo de jogo por partida, ou por tag com o lápis. O Recalbox avisa 5 minutos e
  1 minuto antes do fim e depois sai do jogo; um cartão bónus acrescenta minutos, um número limitado de vezes por dia,
  semana…

Detalhes: [docs/USAGE.md](docs/USAGE.md) (em inglês).

## 🔄 Atualizar

Na página, separador **Atualizações** › **«Atualizar para X»**: a página envia o programa que contém. Os tags e as
definições são mantidos, e a página volta a ligar-se sozinha. Outras formas (ficheiro ZIP, endereço, SSH):
[docs/UPDATING.md](docs/UPDATING.md) (em inglês).

## 🗑️ Desinstalar

- **Recalbox 10**: `START` › Definições avançadas › Scripts do utilizador › **Uninstall-RFID-reader**. Os tags e as
  definições são mantidos, e *Install-RFID-reader* fica no menu para reinstalar com um clique.
- **Tudo, dados incluídos** (SSH): `sh /recalbox/share/system/rfid/uninstall.sh --remove-spi`

## 🩺 Resolução de problemas

| Sintoma | O que fazer |
| --- | --- |
| O Windows propõe «Diagnosticar» em `\\RECALBOX` | perfil de rede *Pública*: mude-o para *Privada*, ou use o endereço IP |
| A página não encontra o Recalbox | mesma rede? experimente o endereço IP em vez de `recalbox.local` |
| «Leitor não encontrado» | ligações, 3,3 V, depois separador **Hardware** › «Testar com um tag» |
| O tag não é lido | tem de ser de 13,56 MHz; um cartão bancário sem contacto permite testar o leitor |
| O botão não faz nada | GPIO17 usado pelos comandos GPIO (`controllers.gpio.enabled=0`), ligação ao GND |
| O jogo não arranca | é preciso o Recalbox 9 ou mais recente; o jogo tem de estar *selecionado*, não uma pasta |
| A página volta a pedir autorização | o Recalbox reiniciou: mantenha o botão da caixa premido 3 segundos |

Guia completo: [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) (em inglês).

## 🛠️ Para programadores

Tudo se testa num PC, sem Raspberry Pi:

```sh
python app/main.py --home ./data config-init
python app/main.py --home ./data simulate      # leitor e botão simulados
python tests/run_tests.py                      # testes unitários, sem hardware
python tools/build_installer.py                # regenera dist/recalbox-rfid-installer.html
```

No Recalbox, a ferramenta de linha de comandos é sempre chamada com `sh` (a partilha exFAT não guarda a permissão de
execução): `sh /recalbox/share/system/rfid/rfidctl help`.

O funcionamento, em resumo:

- **Leitura dos tags**: controlador MFRC522 em Python puro sobre `/dev/spidev0.0` (`ioctl` através de `ctypes`),
  sequência ISO 14443-3A, tolerante a tags clonados.
- **Jogo selecionado**: lido em `/tmp/es_state.inf`, escrito pelo frontend do Recalbox em cada evento.
- **Arranque do jogo**: datagrama UDP `START|<sistema>|<caminho completo>` para `127.0.0.1:1337`, o comando oficial
  do frontend.
- **Página ↔ Recalbox**: um agente WebSocket escrito com a biblioteca padrão; a página é aberta localmente
  (`file://`) e um computador é autorizado com uma pressão física no botão (segredo de sessão em memória).
- **Arranque do sistema**: dois scripts do utilizador permanentes (serviço + agente) e, no Recalbox 10, dois scripts
  do menu (instalar / desinstalar).

Publicação no GitHub (Pages e versões): [docs/PUBLISHING.md](docs/PUBLISHING.md). Os documentos
detalhados de `docs/` e o [histórico de versões](CHANGELOG.md) estão em inglês.

## 📚 Documentação

- [docs/WIRING.md](docs/WIRING.md): ligações em detalhe, escolha dos pinos e luz de estado
- [docs/INSTALLATION.md](docs/INSTALLATION.md): instalação passo a passo (Windows, macOS, Linux)
- [docs/USAGE.md](docs/USAGE.md): associação, cartões para imprimir, cartões especiais, tempo de jogo, comandos, configuração
- [docs/UPDATING.md](docs/UPDATING.md): atualizações e regresso a uma versão anterior
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md): diagnóstico e soluções
- [docs/PUBLISHING.md](docs/PUBLISHING.md): GitHub Pages e versões
