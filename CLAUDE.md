# CLAUDE.md — Sala Livre

API de reserva de salas de reunião (desafio técnico Greenwave). Django + DRF + PostgreSQL.
O objetivo é um código **pleno, simples e defensável**: Prefira clareza a abstração. Nada de repository pattern, hexagonal, CQRS.

## Comandos

```bash
docker compose up --build                      # sobe app + banco (migrate automático)
docker compose run --rm web pytest             # testes (precisam de Postgres)
docker compose run --rm web ruff check .       # lint
docker compose run --rm web ruff format .      # formatação
docker compose run --rm web python manage.py makemigrations
```

### Rodando local (sem Docker)

Alternativa ao Docker: com um ambiente Python já ativado (ferramenta à escolha do dev),
as dependências de `requirements-dev.txt` instaladas e um PostgreSQL acessível conforme o `.env`.
Use o `.env.example` como modelo das configurações locais (`cp .env.example .env` e ajuste);
os valores são lidos via `python-decouple`. Os comandos Docker acima continuam valendo para o avaliador —
**não remover** Dockerfile, `docker-compose.yml`, `entrypoint.sh` nem `.dockerignore`.

```bash
python manage.py migrate && python manage.py seed   # o entrypoint faz isso no Docker
python manage.py runserver
pytest
ruff check .
ruff format .
python manage.py makemigrations
```

Swagger: http://localhost:8000/api/docs/ · Health: http://localhost:8000/api/health

## Stack

- Django 5.2 LTS, DRF, `djangorestframework-simplejwt` (JWT), `drf-spectacular` (OpenAPI),
  `django-filter`, Argon2 para hash de senha.
- **PostgreSQL obrigatório**: a R1 usa `ExclusionConstraint` + extensão `btree_gist`.
  Não há suporte a SQLite, nem nos testes (trade-off consciente).
- Testes: `pytest-django` + `time-machine` (congelar o "agora"). Lint/format: `ruff`.

## Estrutura e responsabilidades

```
config/        settings, urls
core/          BusinessRuleError + exception handler, paginação, permissões, health
accounts/      User customizado (campo role: user|admin), registro, login
rooms/         Room (name, capacity, location, is_active)
reservations/
  models.py        Reservation + constraints do banco
  rules.py         regras PURAS (R2, R3, R4, R6) — recebem `now` por argumento
  availability.py  cálculo PURO de intervalos livres
  services.py      casos de uso: transação, locks, chamada das regras
  serializers.py   só formato/tipos de entrada
  views.py         finas: validam entrada, chamam service, serializam saída
```

Regra de ouro: **serializer valida formato, rules/services aplicam negócio, view só conecta,
banco garante invariantes.** Nunca coloque regra de negócio em view ou serializer.

## Convenções de código

- Choices como `TextChoices` em nível de módulo (`UserRole`, `ReservationStatus`) — nunca
  strings soltas como `"active"` fora deles.
- Funções puras não acessam banco nem chamam `timezone.now()`; o service obtém `now` e repassa.
- Services usam argumentos nomeados (`*`) e aceitam `now=None` para facilitar testes.
- Datas sempre timezone-aware. Banco armazena UTC (timestamptz).
- Nomes de constraints são estáveis e usados no código (`reservation_no_overlap`).

## Regras de negócio e onde cada uma é garantida

| Regra | Descrição | Onde |
|---|---|---|
| R1 | Sem sobreposição de reservas ativas na mesma sala | `ExclusionConstraint reservation_no_overlap` (banco); lock na sala evita deadlock |
| R2 | Não reservar no passado (`start_at > now`) | `rules.validate_time_window` |
| R3 | Duração entre 30 min e 4 h (inclusive) | `rules.validate_time_window` |
| R4 | Entre 07:00 e 20:00 no fuso America/Sao_Paulo, mesmo dia; terminar às 20:00 é permitido | `rules.validate_time_window` |
| R5 | Máx. 3 reservas ativas futuras (`status=active` e `start_at > now`) por usuário | `services.create_reservation` com `select_for_update` no usuário |
| R6 | Cancelar só com >= 1 h de antecedência — vale também para admin | `rules.validate_cancellation` |
| R7 | Sala inativa não aceita novas reservas | `services.create_reservation`, lendo a sala com `select_for_update` |

## Concorrência (ponto central do desafio)

**R1** — `EXCLUDE USING gist (tstzrange(start_at, end_at, '[)') WITH &&, room_id WITH =)
WHERE status = 'active'`. O banco serializa inserts conflitantes no índice; o segundo recebe
`IntegrityError`. Limites `[)`: 09–10 e 10–11 não conflitam. A `CheckConstraint
end_at > start_at` impede ranges vazios que escapariam da exclusão.

**R5** — também tem condição de corrida (duas requisições contam 2 ao mesmo tempo). Dentro de
`transaction.atomic`, travar a linha do usuário com `User.objects.select_for_update().get(pk=...)`
antes de contar. O lock dura até o commit.

**Lock na sala (complemento da R1)** — a constraint sozinha garante a R1, mas dois inserts
conflitantes em paralelo podem dar **deadlock**: cada um insere sua linha, encontra a do outro
(não commitada) ao checar a exclusão e espera por ela. O Postgres aborta um com
`OperationalError` (500, não 409). Reproduzido nos testes de threads (~4 em 11 execuções).
Solução: `Room.objects.select_for_update().get(pk=...)` no início da transação de criação.
Inserts na mesma sala passam a ser sequenciais (sem deadlock) e `is_active` é lido com lock
(R7 sem corrida com admin desativando). O lock **não** substitui a constraint: se algum código
futuro inserir sem pegar o lock, a R1 continua garantida pelo banco.

**Ordem dos locks na criação: sala → usuário.** Qualquer código novo que pegue os dois deve
seguir essa ordem, senão abre deadlock entre os próprios locks. O cancelamento trava só a
reserva.

**Tradução do IntegrityError** — feita FORA da transação (um único `atomic`, sem savepoint):

```python
def create_reservation(**kwargs):
    try:
        return _create_reservation_tx(**kwargs)
    except IntegrityError as e:
        if getattr(e.__cause__.diag, "constraint_name", None) == OVERLAP_CONSTRAINT:
            raise BusinessRuleError("room_unavailable", "...", status_code=409) from e
        raise


@transaction.atomic
def _create_reservation_tx(*, user, room, start_at, end_at, now=None): ...
```

Alternativas descartadas (documentar no README): `if exists()` antes do insert (race),
`select_for_update` na sala **como única garantia** (depende de disciplina do código — por isso
ele é usado só como complemento da constraint), retry em deadlock (laço extra e não resolve a
corrida da R7), SERIALIZABLE (exige retry).

## API

Formato de erro único (via `core.exceptions.api_exception_handler`):

```json
{"error": {"code": "room_unavailable", "message": "Horário já reservado.", "details": {}}}
```

| Situação | HTTP | `error.code` |
|---|---|---|
| Payload malformado / campo faltando (inclui `room` inexistente no POST de reserva) | 400 | `validation_error` |
| Sem token / token inválido | 401 | `not_authenticated` / `token_not_valid` |
| User em ação de admin | 403 | `permission_denied` |
| Recurso inexistente ou de outro usuário (não revela existência) | 404 | `not_found` |
| R1 sobreposição | 409 | `room_unavailable` |
| R5 limite de reservas | 409 | `reservation_limit_reached` |
| Cancelar reserva já cancelada | 409 | `reservation_not_active` |
| R2 início no passado | 422 | `start_in_past` |
| R3 duração fora de 30 min–4 h | 422 | `invalid_duration` |
| R4 fora de 07:00–20:00 / dias diferentes | 422 | `outside_business_hours` |
| R6 cancelamento com menos de 1 h | 422 | `cancellation_too_late` |
| R7 sala inativa (reserva ou disponibilidade) | 422 | `room_inactive` |

422 é o padrão do `BusinessRuleError`; 409 é passado explicitamente via `status_code`.

Endpoints planejados:

```
POST  /api/auth/register            cria sempre role=user
POST  /api/auth/login               JWT; throttle scope "login"
POST  /api/auth/refresh
GET   /api/rooms                    user: só ativas | admin: todas + ?is_active=
POST  /api/rooms                    admin
PATCH /api/rooms/{id}               admin (desativar = is_active=false; sem DELETE)
GET   /api/reservations             user: próprias | admin: todas + ?room=&user=&date_from=&date_to=
POST  /api/reservations
POST  /api/reservations/{id}/cancel cancelamento não apaga: status=cancelled, cancelled_at
GET   /api/rooms/{id}/availability?date=YYYY-MM-DD
GET   /api/health
```

Listagens paginadas (`core.pagination.DefaultPagination`, `?page=&page_size=`).

## Testes

- `rules.py` / `availability.py`: unitários com `parametrize` nos limites
  (29/30 min, 4h/4h01, 06:59, 20:00, 20:01, virada de dia).
- Uma verificação por regra no service/endpoint (status HTTP + `error.code`).
- R1 e R5 concorrentes: `@pytest.mark.django_db(transaction=True)` + `threading.Barrier`,
  checando que só uma reserva foi criada.
- `reservations/tests/test_constraints.py` já prova R1 no banco inserindo direto pelo ORM.
- Permissões: user não cria sala, não vê/cancela reserva alheia.

## Decisões de produto (detalhes e critérios de aceite em `docs/specs/`)

Ambiguidades do enunciado já decididas; todas devem ir para o README.

- **R5**: reserva em andamento (`start_at <= now < end_at`) não conta como futura.
- **R6**: vale também para admin. Reserva já cancelada → 409 `reservation_not_active`.
  O cancelamento trava a linha da reserva (`select_for_update`).
- **Criação**: ordem das validações = payload (400) → R7 → R2/R3/R4 → R5 → R1 (no INSERT);
  devolve a primeira violação. `end_at <= start_at` cai na R3. Datas sem fuso são
  interpretadas em America/Sao_Paulo.
- **Salas**: user lista só ativas; admin lista todas e filtra por `?is_active=`.
- **Listagem de reservas**: inclui canceladas. `date_from`/`date_to` inclusivos, sobre a data
  local de `start_at`. Filtros enviados por user são ignorados.
- **Disponibilidade**: sala inativa → 422 `room_inactive`. Janela = `max(07:00, now)`–20:00;
  dia passado → `[]`. O recorte por `now` é feito por quem chama `free_intervals` (que segue
  pura). Intervalos livres < 30 min são devolvidos.
- **Admin** não é criado pela API (seed, `createsuperuser` ou Django Admin).

## Decisões em aberto / a documentar no README

- Seed: `core/management/commands/seed.py` (admin/Admin@123, ana e bruno/User@123, 4 salas,
  uma inativa). Idempotente; o entrypoint roda se `SEED=1`. Não cria reservas.
- Bônus previstos: seed, health check (feito), rate limit no login. Cache, CI, deploy e
  frontend ficam em "o que faria com mais tempo".
- Registrar no README onde a IA ajudou.
