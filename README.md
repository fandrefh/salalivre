# Sala Livre

API de reserva de salas de reunião.

Django 5.2 + Django REST Framework + PostgreSQL. Autenticação JWT, documentação OpenAPI.

## Como rodar

Há dois caminhos: **Docker** (recomendado, sobe app e banco com um comando) ou **local**, com
um ambiente Python e um PostgreSQL já instalados. Nos dois, as configurações vêm de variáveis
de ambiente; o modelo é o [`.env.example`](.env.example).

> **PostgreSQL é obrigatório** (inclusive nos testes): a regra de não sobreposição (R1) usa
> `ExclusionConstraint` com a extensão `btree_gist`, que não existe no SQLite.

### Opção 1 — Docker

Requisitos: Docker com Compose v2.

```bash
cp .env.example .env        # opcional; sem ele, valem os padrões do docker-compose.yml
docker compose up --build
```

O entrypoint aplica as migrations e roda o seed (`SEED=1`) automaticamente.

### Opção 2 — Local

Requisitos: Python 3.12+ e PostgreSQL 14+.

1. Crie e ative um ambiente virtual com a ferramenta de sua preferência e instale as
   dependências:

   ```bash
   pip install -r requirements-dev.txt
   ```

2. Crie o usuário e o banco no PostgreSQL. O usuário precisa de `CREATEDB` (o pytest cria um
   banco de teste) e ser dono do banco (a migration cria a extensão `btree_gist`, que é
   *trusted* a partir do PostgreSQL 13):

   ```bash
   createuser --createdb --pwprompt salalivre
   createdb --owner=salalivre salalivre
   ```

3. Configure o ambiente e ajuste `POSTGRES_*` conforme o passo anterior:

   ```bash
   cp .env.example .env
   ```

4. Aplique as migrations, carregue o seed e suba o servidor:

   ```bash
   python manage.py migrate
   python manage.py seed
   python manage.py runserver
   ```

### Endereços

- API: http://localhost:8000/api/
- Documentação interativa (Swagger): http://localhost:8000/api/docs/
- Schema OpenAPI: http://localhost:8000/api/schema/
- Health check: http://localhost:8000/api/health
- Django Admin: http://localhost:8000/admin/

### Dados de exemplo (seed)

O comando `python manage.py seed` cria os dados abaixo (no Docker, roda sozinho com `SEED=1`).
É idempotente: rodar de novo não duplica nada nem redefine senhas.

| Usuário | Senha | Papel |
|---|---|---|
| `admin` | `Admin@123` | admin (também acessa o Django Admin em `/admin/`) |
| `ana` | `User@123` | user |
| `bruno` | `User@123` | user |

Salas: Sala Azul, Sala Verde, Auditório e **Sala Laranja (inativa)**, para testar a R7.
Não há reservas no seed, porque elas dependem da data atual e ficariam no passado.

## Como rodar os testes

```bash
# Docker
docker compose run --rm web pytest
docker compose run --rm web ruff check .

# Local (ambiente ativado e PostgreSQL configurado no .env)
pytest
ruff check .
```

Os testes congelam o relógio (`time-machine`) ou recebem `now` por argumento, então não
dependem da data em que rodam. Os testes de concorrência (R1 e R5) usam threads com conexões
reais ao banco.

| Arquivo | Cobre |
|---|---|
| `reservations/tests/test_rules.py` | R2, R3, R4, R6 — limites de cada regra pura (29/30 min, 4h/4h01, 06:59, 20:00, 20:01, virada de dia, fusos) |
| `reservations/tests/test_availability.py` | Cálculo de intervalos livres (função pura) |
| `reservations/tests/test_constraints.py` | R1 garantida pelo banco, inserindo direto pelo ORM |
| `reservations/tests/test_services.py` | R1–R7 com banco, ordem das validações, cancelamento e **concorrência** (R1 e R5) |
| `reservations/tests/test_views.py` | Contrato HTTP: autenticação, escopo por papel, filtros, paginação, códigos de erro |
| `accounts/tests/` | Cadastro, login, refresh, rate limit, criação de admin |
| `core/tests/` | Formato de erro, health check, seed |

## Endpoints

Documentação completa e testável em http://localhost:8000/api/docs/ (use **Authorize** com o
`access` do login). Exemplos abaixo com o seed carregado.

Todos os endpoints, exceto cadastro, login, refresh e health, exigem
`Authorization: Bearer <access>`. Datas seguem ISO 8601; sem fuso, são interpretadas em
`America/Sao_Paulo`, e as respostas vêm sempre nesse fuso.

### Formato de erro

Todo erro tem o mesmo formato:

```json
{"error": {"code": "room_unavailable", "message": "Horário já reservado para esta sala.", "details": {}}}
```

| Situação | HTTP | `error.code` |
|---|---|---|
| Payload ou parâmetro inválido (detalhes por campo em `details`) | 400 | `validation_error` |
| Sem token / token inválido / credenciais erradas | 401 | `not_authenticated` / `token_not_valid` / `no_active_account` |
| Usuário comum em ação de admin | 403 | `permission_denied` |
| Recurso inexistente **ou de outro usuário** (não revela existência) | 404 | `not_found` |
| R1 — horário já reservado na sala | 409 | `room_unavailable` |
| R5 — limite de 3 reservas ativas futuras | 409 | `reservation_limit_reached` |
| Cancelar reserva já cancelada | 409 | `reservation_not_active` |
| R2 — início no passado | 422 | `start_in_past` |
| R3 — duração fora de 30 min a 4 h | 422 | `invalid_duration` |
| R4 — fora de 07:00–20:00 ou em dias diferentes | 422 | `outside_business_hours` |
| R6 — cancelamento com menos de 1 h de antecedência | 422 | `cancellation_too_late` |
| R7 — sala inativa | 422 | `room_inactive` |
| Excesso de tentativas de login | 429 | `throttled` |

### Autenticação

**`POST /api/auth/register`** — cria sempre um usuário com `role=user` (um `role` enviado é
ignorado).

```json
// requisição
{"username": "carla", "email": "carla@example.com", "password": "Segura@2030"}

// 201
{"id": 4, "username": "carla", "email": "carla@example.com", "role": "user"}
```

**`POST /api/auth/login`** — limitado a 5 tentativas por minuto por IP (`LOGIN_THROTTLE_RATE`).

```json
// requisição
{"username": "ana", "password": "User@123"}

// 200
{"access": "eyJhbGciOi...", "refresh": "eyJhbGciOi..."}
```

**`POST /api/auth/refresh`** — `access` vale 30 min; `refresh`, 1 dia.

```json
// requisição
{"refresh": "eyJhbGciOi..."}

// 200
{"access": "eyJhbGciOi..."}
```

Fluxo completo com `curl`:

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "ana", "password": "User@123"}' | python -c "import sys, json; print(json.load(sys.stdin)['access'])")

curl -s http://localhost:8000/api/reservations -H "Authorization: Bearer $TOKEN"
```

### Salas

> Não implementados nesta entrega — ver [O que ficou de fora](#o-que-ficou-de-fora-e-o-que-faria-com-mais-tempo).
> Enquanto isso, as salas são geridas pelo Django Admin (`/admin/`) e o seed cria quatro
> salas: Sala Azul, Sala Verde, Auditório e Sala Laranja (inativa).

### Reservas

**`POST /api/reservations`** — a reserva é sempre de quem está autenticado.

```json
// requisição
{"room": 1, "start_at": "2030-01-10T09:00:00-03:00", "end_at": "2030-01-10T10:00:00-03:00"}

// 201
{
  "id": 1,
  "room": 1,
  "user": 2,
  "start_at": "2030-01-10T09:00:00-03:00",
  "end_at": "2030-01-10T10:00:00-03:00",
  "status": "active",
  "cancelled_at": null,
  "created_at": "2030-01-09T12:00:00-03:00"
}

// 409 — outra reserva ativa ocupa parte do horário
{"error": {"code": "room_unavailable", "message": "Horário já reservado para esta sala.", "details": {}}}
```

**`GET /api/reservations`** — paginado (`?page=`, `?page_size=` até 100). Usuário comum vê
só as próprias reservas. Admin vê todas e pode filtrar por `?room=`, `?user=`,
`?date_from=YYYY-MM-DD` e `?date_to=YYYY-MM-DD` (inclusivos, pela data local de início).
Reservas canceladas aparecem com `status: "cancelled"`.

```json
// GET /api/reservations?room=1&date_from=2030-01-10&date_to=2030-01-10  (admin)
// 200
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "room": 1,
      "user": 2,
      "start_at": "2030-01-10T09:00:00-03:00",
      "end_at": "2030-01-10T10:00:00-03:00",
      "status": "active",
      "cancelled_at": null,
      "created_at": "2030-01-09T12:00:00-03:00"
    }
  ]
}
```

**`POST /api/reservations/{id}/cancel`** — sem corpo. Não apaga o registro. Usuário comum
cancela só as próprias; admin cancela qualquer uma. A R6 vale para os dois.

```json
// 200
{
  "id": 1,
  "room": 1,
  "user": 2,
  "start_at": "2030-01-10T09:00:00-03:00",
  "end_at": "2030-01-10T10:00:00-03:00",
  "status": "cancelled",
  "cancelled_at": "2030-01-09T12:00:00-03:00",
  "created_at": "2030-01-09T12:00:00-03:00"
}

// 422 — faltando menos de 1 h para o início
{"error": {"code": "cancellation_too_late", "message": "A reserva só pode ser cancelada com pelo menos 1 hora de antecedência.", "details": {}}}
```

### Disponibilidade

**`GET /api/rooms/{id}/availability?date=YYYY-MM-DD`** — intervalos livres entre 07:00 e
20:00 do dia, considerando só reservas ativas. Para o dia atual, começa no horário corrente;
dia passado devolve lista vazia. Sala inativa responde 422 `room_inactive`.

```json
// GET /api/rooms/1/availability?date=2030-01-10  (com uma reserva das 09:00 às 10:00)
// 200
{
  "room": 1,
  "date": "2030-01-10",
  "free": [
    {"start_at": "2030-01-10T07:00:00-03:00", "end_at": "2030-01-10T09:00:00-03:00"},
    {"start_at": "2030-01-10T10:00:00-03:00", "end_at": "2030-01-10T20:00:00-03:00"}
  ]
}
```

### Health check

**`GET /api/health`** — público; verifica a conexão com o banco.

```json
// 200
{"status": "ok", "database": "up"}

// 503
{"status": "error", "database": "down"}
```

## Decisões de arquitetura

As decisões abaixo são minhas; a IA ajudou a implementá-las (ver [Uso de IA](#uso-de-ia)). O
objetivo foi um código simples e defensável: clareza acima de abstração, sem repository
pattern, arquitetura hexagonal ou CQRS, que não se pagam num projeto deste tamanho.

### Stack

- **Django 5.2 LTS + Django REST Framework** — migrations versionadas, ORM com suporte nativo
  às constraints do PostgreSQL (`ExclusionConstraint` em `django.contrib.postgres`), Django
  Admin pronto para operação e bibliotecas maduras para JWT (`simplejwt`) e OpenAPI
  (`drf-spectacular`).
- **PostgreSQL obrigatório, inclusive nos testes** — a R1 é garantida no banco (ver
  [Concorrência da R1](#concorrência-da-r1)). Testar no mesmo banco de produção é o que permite
  provar a concorrência de verdade; foi assim que um deadlock real apareceu e foi corrigido.

### Separação de responsabilidades

| Camada | Responsabilidade |
|---|---|
| `serializers.py` | Só formato e tipos de entrada/saída. Nenhuma regra de negócio. |
| `rules.py` | Regras **puras** (R2, R3, R4, R6): sem banco e sem relógio — `now` chega por argumento. |
| `availability.py` | Cálculo **puro** dos intervalos livres. |
| `services.py` | Casos de uso: transação, locks, ordem das validações, tradução de erros do banco. |
| `views.py` | Finas: validam a entrada, chamam o service, serializam a saída. |
| Banco | Invariantes que não podem depender do código: sobreposição (R1), `end_at > start_at`, capacidade > 0, unicidade. |

Por quê: as regras ficam num lugar só e são testadas sem banco, em milissegundos e sem
depender da data em que o teste roda. As views não decidem nada, então trocar a interface (ex.:
um comando ou uma fila) não exigiria reescrever regra.

### Modelagem

- **Reserva** guarda `start_at`/`end_at` como `timestamptz` (UTC no banco) e um `status`
  (`active` | `cancelled`). **Cancelar não apaga**: muda o status e grava `cancelled_at`,
  preservando o histórico e liberando o horário (a R1 só considera reservas ativas).
- **Sala** não é apagada: desativar é `is_active=false`. Reservas existentes seguem válidas, e
  as chaves estrangeiras usam `PROTECT` para impedir exclusão acidental com histórico.
- **Papéis** como um campo `role` (`user` | `admin`) no usuário, em vez de grupos e
  permissões do Django: são só dois papéis fixos, e um campo é mais simples de ler e testar.
- Valores fixos como `TextChoices` (`UserRole`, `ReservationStatus`), nunca strings soltas.

### Fuso horário

O banco armazena em UTC; as regras de horário comercial (R4) e a disponibilidade são avaliadas
em `America/Sao_Paulo`. O fuso de negócio vem de um único lugar (`settings.TIME_ZONE`): é o
mesmo em que o DRF interpreta datas enviadas sem fuso, então as duas coisas não podem
divergir.

### API e erros

- Um formato único de erro (`{"error": {"code", "message", "details"}}`), com `code` estável
  para o cliente tratar sem depender do texto.
- **422** para regra de negócio violada com entrada bem formada (R2, R3, R4, R6, R7) e
  **409** para conflito com o estado atual (R1, R5, reserva já cancelada).
- **404**, e não 403, para reserva de outro usuário: não revela que ela existe.
- Cadastro público cria sempre `role=user`; admin vem do seed, do `createsuperuser` ou do
  Django Admin, para não haver escalada de privilégio pela API.

### Ambiguidades do enunciado

Cada ambiguidade virou uma decisão registrada nas specs (`docs/specs/`, marcadas como
**[DECISÃO]**). As principais:

- **R5:** reserva em andamento não conta como "futura".
- **R6:** vale também para admin (o enunciado não abre exceção).
- **Ordem das validações:** R7 → R2/R3/R4 → R5 → R1; a primeira violação é a devolvida.
- **Salas inativas:** disponibilidade de sala inativa responde 422. Para a listagem de salas,
  ficou decidido que usuário comum veria só as ativas (endpoint não implementado — ver
  [O que ficou de fora](#o-que-ficou-de-fora-e-o-que-faria-com-mais-tempo)).
- **Disponibilidade de hoje** começa no horário atual (não oferece horário que a R2 recusaria).

## Concorrência da R1

> R1: duas reservas ativas não podem se sobrepor na mesma sala — inclusive quando duas
> requisições chegam ao mesmo tempo.

### Garantia: constraint de exclusão no PostgreSQL

A regra é garantida pelo **banco**, não pelo código da aplicação:

```sql
EXCLUDE USING gist (
    tstzrange(start_at, end_at, '[)') WITH &&,  -- intervalos que se sobrepõem
    room_id WITH =                               -- na mesma sala
) WHERE (status = 'active')                      -- só reservas ativas
```

- `[)` = início incluso, fim excluso: 09:00–10:00 e 10:00–11:00 **não** conflitam.
- `WHERE status = 'active'`: reserva cancelada libera o horário sem apagar o registro.
- `btree_gist` permite comparar `room_id` com `=` no mesmo índice GiST.
- Uma `CHECK (end_at > start_at)` impede intervalos vazios, que escapariam da exclusão.

Quando dois inserts conflitam, o Postgres aceita um e rejeita o outro com `IntegrityError`.
O service identifica a constraint pelo nome (`reservation_no_overlap`) e devolve
**409 `room_unavailable`**. Essa tradução é feita fora da transação, depois do rollback, sem
precisar de savepoint.

Como a garantia está no banco, ela vale para qualquer caminho de escrita (API, Django Admin,
shell, um script futuro). `reservations/tests/test_constraints.py` prova isso inserindo direto
pelo ORM, sem passar pelo service.

### Complemento: lock na sala (e por quê)

Nos testes concorrentes (threads + `threading.Barrier` disparando 6 requisições para o mesmo
horário), a constraint sempre manteve **uma única reserva**, mas em algumas execuções uma das
requisições recebia `deadlock detected` (500) em vez de 409. Motivo: cada transação insere sua
linha, encontra a do outro (ainda não commitada) ao checar a exclusão e espera por ela — as
duas esperam uma pela outra, e o Postgres aborta uma.

Solução: a transação de criação começa com `SELECT ... FOR UPDATE` na linha da sala. Inserts
na mesma sala passam a ser sequenciais, e o perdedor recebe o 409 correto. Efeitos:

- **Não substitui a constraint.** O lock evita o deadlock; quem garante a R1 continua sendo o banco.
- **R7 sem corrida:** `is_active` é lido sob lock, então um admin desativando a sala no mesmo
  instante não deixa uma reserva passar.
- **Custo:** reservas da mesma sala esperam umas pelas outras por alguns milissegundos, mesmo
  em horários diferentes. Irrelevante para o volume de uma agenda de salas.

A R5 (máximo de 3 reservas futuras) tem a mesma classe de problema e usa o mesmo recurso:
`SELECT ... FOR UPDATE` na linha do **usuário** antes de contar. **Ordem fixa dos locks:
sala → usuário**, para que os próprios locks não gerem deadlock.

### Alternativas descartadas

| Alternativa | Por que não |
|---|---|
| `if exists()` antes do INSERT | Race condition clássica: as duas requisições verificam antes de qualquer uma inserir. É exatamente o que o enunciado diz não ser suficiente. |
| Só `SELECT FOR UPDATE` na sala, sem constraint | Funciona só enquanto todo código que grava reservas lembrar de pegar o lock. A constraint não depende de disciplina. |
| Retry automático em deadlock | Resolve o 500, mas adiciona um laço de retentativa e não resolve a corrida da R7. |
| Isolamento `SERIALIZABLE` | Exige retry em toda falha de serialização e afeta todas as queries da transação. |

## O que ficou de fora e o que faria com mais tempo

Priorizei as regras de negócio, a concorrência e os testes, seguindo a orientação de entregar
menos escopo com mais qualidade.

### Endpoints de salas (requisito 1.2)

Os endpoints HTTP de salas não foram implementados nesta entrega:

- `GET /api/rooms` — listagem paginada; usuário comum veria só salas ativas, admin veria todas
  com filtro `?is_active=`.
- `POST /api/rooms` e `PATCH /api/rooms/{id}` — criar, editar e desativar (`is_active=false`),
  só para admin. Sem `DELETE`: sala não é apagada.

O que já existe e cobre o uso enquanto isso:

- O **model** `Room` com as regras de dados (nome único, capacidade > 0), e a **R7** completa:
  sala inativa não aceita reserva e reservas existentes continuam válidas — tudo testado.
- O **seed** cria quatro salas (uma inativa) com IDs conhecidos para usar nas reservas.
- O **Django Admin** (`/admin/`, usuário `admin`) permite listar, criar, editar e desativar
  salas.
- As permissões já estão prontas em `core/permissions.py` (`IsAdminOrReadOnly`).

Com mais tempo, seria um `ModelViewSet` sem `destroy`, com o queryset filtrado por papel e a
permissão acima — a mesma estrutura das reservas.

### Bônus não feitos

- **Cache na disponibilidade**, por sala e dia, invalidado ao criar ou cancelar reserva
  daquela sala.
- **Pipeline de CI** rodando `ruff` e `pytest` com um serviço PostgreSQL.
- **Deploy** em ambiente público.
- **Frontend** mínimo (calendário ou lista com formulário).
- **Logs estruturados em JSON.** Hoje os logs são texto simples; o health check, que faz parte
  do mesmo bônus, foi feito.

### Funcionalidades

- **Editar uma reserva** (mudar horário ou sala). Hoje o caminho é cancelar e criar outra.
- **Recuperação e troca de senha.**
- **Logout com invalidação do token** (blacklist do `simplejwt`). Hoje o `access` vale até
  expirar (30 min).
- **Notificação ao dono** quando um admin cancela a reserva dele.

### Operação

- **Redis** como cache compartilhado, para o contador do rate limit valer entre processos
  (ver trade-offs).
- **gunicorn** no Docker no lugar do `runserver`, que é servidor de desenvolvimento.

## Trade-offs aceitos

Escolhas feitas de propósito, sabendo o que se perde em cada uma.

| Escolha | O que ganho | O que perco |
|---|---|---|
| **PostgreSQL obrigatório, sem suporte a SQLite** (nem nos testes) | A R1 é garantida pelo banco, e os testes de concorrência rodam no banco real — foi assim que o deadlock apareceu. | Rodar fora do Docker exige um PostgreSQL instalado e configurado. |
| **Lock na sala ao criar reserva** | Sem deadlock entre pedidos simultâneos (o perdedor recebe 409, não 500) e sem corrida na R7. | Reservas da mesma sala esperam umas pelas outras por milissegundos, mesmo em horários diferentes. Irrelevante para o volume de uma agenda de salas. |
| **Contador do rate limit no cache em memória** (padrão do Django) | Nenhuma infraestrutura extra. | Cada processo conta separado: com vários workers, o limite real de 5/min por IP se multiplica pelo número de workers. A solução é Redis. |
| **R6 vale também para admin** | Regra única e fácil de defender; o enunciado não abre exceção. | O admin não consegue cancelar uma reserva em cima da hora numa emergência. |
| **Datas sem fuso lidas como horário de São Paulo** | Conveniente para clientes que enviam só a hora local. | Aceita uma entrada ambígua em vez de exigir o fuso explícito. |
| **Unicidade de e-mail diferencia maiúsculas** | Usa a constraint padrão, sem normalização extra. | `Ana@x.com` e `ana@x.com` podem coexistir como contas diferentes. |
| **Mensagens do `simplejwt` em inglês** | Nenhum código extra de tradução. | Alguns erros de autenticação vêm em inglês enquanto o resto da API está em português. O `error.code`, que é o que o cliente deve usar, é estável. |

## Uso de IA

Usei o Claude Code (Anthropic), com o modelo Claude Opus, como assistente durante o
desenvolvimento, no modelo "eu decido, a IA propõe e implementa sob revisão". Toda mudança de
código foi apresentada com o raciocínio, e as decisões de produto e de arquitetura foram
minhas — várias propostas da IA foram questionadas, ajustadas ou recusadas antes de entrar.

O trabalho teve duas fases:

1. **Planejamento e estrutura inicial** — o planejamento foi meu: stack, separação de
   responsabilidades (regras puras × services × views finas) e a estratégia para a R1 com
   `ExclusionConstraint`, registrados no `CLAUDE.md`, que serviu de guia para a IA no resto do
   projeto. A estrutura inicial (models e constraints, `core` com formato de erro, permissões,
   paginação e health check, seed e Docker) foi parte escrita por mim e parte com ajuda da IA.
2. **Regras de negócio, API e testes** — a partir do enunciado transcrito em specs, a IA
   implementou e testou o restante sob minha revisão, como detalhado abaixo.

**Onde a IA ajudou de forma relevante:**

- **Specs (`docs/specs/`)** — transcrição do enunciado em uma spec por funcionalidade, seguindo
  um template meu, com as ambiguidades levantadas e marcadas para decisão (ex.: reserva em
  andamento conta para a R5? R6 vale para admin? disponibilidade de sala inativa?).
- **Implementação** — `rules.py`, `availability.py`, `services.py` e a camada HTTP de reservas
  e de autenticação, seguindo as convenções definidas no `CLAUDE.md` do projeto.
- **Testes** — escrita dos testes de regras, disponibilidade, services (incluindo os
  concorrentes com threads), endpoints e autenticação.
- **Problemas encontrados pelos testes**, analisados junto com a IA:
  - **Deadlock na R1 sob concorrência** — a constraint garantia a regra, mas um dos pedidos
    recebia 500 em vez de 409 em ~4 de 11 execuções. Avaliamos três saídas (lock na sala,
    retry, mapear deadlock para 409); escolhi o lock na sala (ver "Concorrência da R1").
  - **Filtro de data aceitando formato pt-BR** (`10/01/2030`) por causa do `LANGUAGE_CODE`,
    divergindo da spec — restringido a ISO 8601.
  - **`createsuperuser` criando admin sem `role=admin`** — corrigido com um `UserManager`.
  - **Rate limit não testável com `override_settings`** (o DRF copia as taxas para um atributo
    de classe na importação).
- **Documentação** — rascunho deste README.

**Onde eu intervim / decidi:**

- Escolha da estratégia de concorrência e das regras ambíguas do enunciado.
- Revisão de propostas da IA — ex.: a IA havia fixado o fuso da R4 numa constante própria;
  questionei e trocamos por `settings.TIME_ZONE`, porque o fuso em que o DRF interpreta datas
  sem fuso e o fuso da R4 precisam ser o mesmo.
- Escopo: o que entra, o que fica para "com mais tempo", e quando parar para escrever testes.

Todo o código foi revisado e consigo explicá-lo linha a linha.
