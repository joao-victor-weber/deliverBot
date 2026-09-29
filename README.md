# DeliveryBot — pedidos de restaurante via WhatsApp

Projeto acadêmico do **Tema 09 — DeliveryBot**. O sistema organiza pedidos de restaurante, registra clientes e itens, apresenta uma fila de preparo para a cozinha e gera notificações conforme o pedido avança. Para entrega, utiliza a **API ViaCEP** na consulta de endereço e na verificação do município atendido.

**Repositório:** https://github.com/joao-victor-weber/deliverBot

> Estado da validação: em 28/09/2026, a execução local compartilhada pelo grupo apresentou **9 testes automatizados aprovados** e demonstrou manualmente o fluxo de entrega em modo de mensagens simuladas. Isso não constitui certificação para uso em produção nem comprova o envio por um provedor real de WhatsApp.

## Funcionalidades

- Cardápio carregado de `data/cardapio.json` para a tabela `produtos` na inicialização do banco; listagem dos produtos ativos na página de pedidos.
- Atendimento por menu numerado, geração de **link individual** com expiração e impedimento de reutilização após o pedido.
- Registro do cliente, pedido, itens, modalidade (entrega/retirada), pagamento, valores e taxa de entrega.
- Consulta de CEP pela ViaCEP e validação do município informado em `CIDADES_ATENDIDAS` quando a modalidade for `ENTREGA`.
- Mensagens de confirmação, previsão aproximada, recibo marcado **DOCUMENTO NÃO FISCAL** e avisos de status.
- Painel `/cozinha`, com atualização automática da página e avanço manual das etapas de preparo e entrega.
- Histórico de mensagens de entrada e saída na tabela `mensagens`.
- Três opções de envio: `TESTE` (terminal), `WAHA` (integração opcional) e `META` (Cloud API opcional).

## Fluxos do pedido

**Entrega:** `AGUARDANDO → EM_PREPARO → PRONTO → SAIU_PARA_ENTREGA → ENTREGUE`.

**Retirada no balcão:** `AGUARDANDO → EM_PREPARO → PRONTO → RETIRADO`.

No registro do pedido, o sistema gera confirmação e tempo estimado. Quando a modalidade é entrega, a etapa `PRONTO` é comunicada como preparação para o envio, e `SAIU_PARA_ENTREGA` gera o aviso de saída ao cliente. A fila deixa de listar pedidos finalizados.

## Tecnologias e dependências

- Python 3.12 (ambiente utilizado nos testes informados pelo grupo).
- Flask 3.0.3 — aplicação web e rotas HTTP.
- SQLite — persistência relacional local.
- Requests 2.32.3 — consultas HTTP, inclusive ViaCEP.
- python-dotenv 1.0.1 — leitura da configuração de ambiente.
- pytest 8.3.3 — testes automatizados.
- HTML e templates Jinja — formulários e painel da cozinha.
- Docker Compose, WAHA e n8n — integrações opcionais de mensagens/automação; **não são necessários no modo TESTE**.

As versões das bibliotecas estão fixadas em `requirements.txt`.

## Instalação no Windows (PowerShell)

Execute na pasta raiz do repositório:

```powershell
git clone https://github.com/joao-victor-weber/deliverBot.git
cd deliverBot
py -3.12 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Se o comando `py -3.12` não estiver disponível e já houver Python instalado, utilize `python -m venv venv`. Se a ativação for bloqueada pelo PowerShell, use `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` somente no terminal atual e tente ativar novamente.

No `.env`, revise **antes de fazer um pedido de entrega**:

```dotenv
WHATSAPP_PROVIDER=TESTE
BASE_URL=http://localhost:5000
DATABASE_PATH=data/deliverybot.db
TEMPO_PREPARO_MIN=40
TAXA_ENTREGA=6.00
CIDADES_ATENDIDAS=União da Vitória
```

**Atenção à acentuação:** use a grafia do município devolvida pela ViaCEP; `Uniao da Vitoria` sem acentos pode não coincidir com `União da Vitória`. Para atender mais de um município, separe-os por vírgula. A checagem implementada é **por município**, não por distância em quilômetros; a presença de `RAIO_ENTREGA_KM` no arquivo de configuração não significa que esse raio seja aplicado na validação atual.

Nunca publique o `.env` com tokens, chaves ou telefones reais. O arquivo `.env.example` contém apenas valores de exemplo.

## Execução e demonstração local

```powershell
python -m src.app
```

Acesse `http://127.0.0.1:5000/testar` para simular a geração de um link de pedido e `http://127.0.0.1:5000/cozinha` para acompanhar a fila. Em modo `TESTE`, as notificações aparecem no terminal com o marcador `[MODO TESTE]` e **não são mensagens entregues pelo WhatsApp**.

Roteiro de demonstração:

1. Abra `/testar`, selecione produto e modalidade `ENTREGA`, informe um CEP de município permitido e conclua o pedido.
2. Confira no terminal a confirmação, o recibo não fiscal e o prazo estimado.
3. Abra `/cozinha` e avance para `EM_PREPARO`, `PRONTO`, `SAIU_PARA_ENTREGA` e `ENTREGUE`.
4. Confira a notificação de saída para entrega e a saída do pedido finalizado da fila.
5. Em uma tentativa separada, informe CEP válido de município não atendido e confirme a rejeição. O resultado desta tentativa deve ser capturado como evidência antes da entrega acadêmica.
6. Teste também a modalidade `RETIRADA BALCAO`, cujo encerramento correto é `RETIRADO`.

A rota `/testar` e o servidor Flask com depuração ativa destinam-se **exclusivamente ao desenvolvimento**; não exponha esse servidor na internet.

## API ViaCEP

Requisição HTTP realizada pelo módulo `src/viacep.py`:

```text
GET https://viacep.com.br/ws/{cep}/json/
```

O módulo remove a pontuação do CEP, exige oito dígitos, consulta o serviço, interpreta a resposta e utiliza `localidade` e `uf` para compor o endereço e verificar a cidade configurada. Retornos inválidos, inexistentes ou falha de consulta impedem o pedido de entrega. Não há cálculo de geolocalização ou quilometragem nessa integração.

**Documentação oficial:** https://viacep.com.br/

## Principais rotas HTTP

| Método | Rota | Finalidade |
|---|---|---|
| GET | `/testar` | Simulação local e criação do link individual |
| GET | `/m/<token>` | Exibição do formulário/cardápio para um token válido |
| POST | `/m/<token>` | Cadastro do pedido e notificações iniciais |
| GET | `/cozinha` | Visualização da fila |
| POST | `/cozinha/avancar/<pedido_id>` | Avanço de status |
| GET/POST | `/webhook` | Verificação/recebimento da Meta Cloud API |
| POST | `/webhook/waha` | Recebimento de eventos WAHA |
| POST | `/api/bot/mensagem` | Processamento de mensagem para a integração n8n |

`<token>` e `<pedido_id>` são parâmetros de rota, não valores fixos.

## Banco de dados

**Banco:** SQLite. **Definição:** `sql/schema.sql`. **Inicialização:** `src/db.py`. **Cardápio inicial:** `data/cardapio.json`.

| Entidade | Finalidade e vínculo principal |
|---|---|
| `clientes` | Identificação e contato do cliente; referenciada por `pedidos` |
| `produtos` | Catálogo, categorias, preço e indicador de atividade |
| `pedidos` | Modalidade, pagamento, prazo, totais, status; referência ao cliente |
| `itens_pedido` | Produtos, quantidades e preço unitário vinculados ao pedido |
| `fila_preparo` | Ordem e status de preparo, com um registro por pedido |
| `mensagens` | Registro de comunicação de entrada/saída por telefone |
| `links_pedido` | Token único, expiração, uso e pedido correspondente |
| `sessoes_bot` | Estado do atendimento por telefone |

As **seis primeiras** são as entidades mínimas especificadas pelo professor; as duas últimas suportam o fluxo de atendimento. A definição do banco fica versionada, mas arquivos de banco preenchidos com dados reais devem ser mantidos fora do versionamento.

## Estrutura de pastas (resumo)

```text
src/                 lógica da aplicação e integrações
web/templates/       formulário e painel de cozinha
sql/schema.sql       estrutura do banco
data/cardapio.json   cardápio inicial
n8n/                 workflow opcional de integração WAHA
tests/              testes automatizados
.env.example         exemplo de configuração sem segredos
requirements.txt     dependências Python
docker-compose.yml   serviços opcionais WAHA/n8n
```

## Testes

```powershell
python -m pytest -v
```

Em 28/09/2026, o grupo apresentou execução local com **9 testes aprovados**. A suíte inclui número do pedido, cálculo de valores e taxa, unicidade e invalidação do link, avanço da fila, conteúdo do recibo, sequência completa da entrega e texto das notificações de entrega. Os testes não substituem demonstrações do ViaCEP com resposta real nem teste de envio de mensagem por provedor externo.

## Integrações opcionais e segurança

O projeto disponibiliza configuração para WAHA/n8n por `docker compose` e para Meta Cloud API por variáveis de ambiente. Para essas opções, consulte o `docker-compose.yml`, `n8n/deliverybot-waha.json` e as configurações de `src/config.py`/`src/whatsapp.py`.

- Antes de publicar ou expor a infraestrutura, **substitua qualquer credencial demonstrativa presente no Compose**, configure autenticação e restrinja acesso à cozinha, ao endpoint de teste e aos serviços auxiliares.
- Nunca reutilize as credenciais de exemplo em serviços expostos.
- Evite versionar `.env`, bancos reais, logs e dados de clientes.
- O modo `TESTE` é suficiente para demonstrar os requisitos acadêmicos sem integrar um número pessoal ao WhatsApp.

## Escopo e limitações

Este repositório é um protótipo acadêmico. O cardápio é cadastrado inicialmente por seed JSON/SQLite; não se deve descrever a interface atual como um painel administrativo completo de CRUD. A restrição geográfica de entrega utiliza o nome do município fornecido pelo ViaCEP, não um cálculo de raio. O painel e o servidor de desenvolvimento não demonstram autenticação ou endurecimento para operação pública. Os testes documentados ocorreram no ambiente local, predominantemente no modo `TESTE`.

## Fontes oficiais e documentação

- Repositório do grupo: https://github.com/joao-victor-weber/deliverBot
- ViaCEP: https://viacep.com.br/
- Flask: https://flask.palletsprojects.com/en/stable/
- Python / SQLite: https://docs.python.org/3/library/sqlite3.html
- pytest: https://docs.pytest.org/en/stable/
- Manual de Normas Técnicas para Trabalhos Acadêmicos – Coligadas UB: https://laranjeiras.camporeal.edu.br/content/uploads/2023/11/Manual-de-Normas-Tecnicas-para-Trabalhos-Academicos-Coligadas-UB.pdf

**Grupo:** preencher os nomes completos e os dados institucionais no relatório acadêmico, conforme orientações do professor.
