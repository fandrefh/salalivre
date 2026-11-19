# Spec: Criar reserva

## Contexto
> Por que essa funcionalidade existe? Qual problema resolve?
> Qual o impacto se não for feita?

É o problema central do desafio: na planilha, duas pessoas reservam a mesma sala no mesmo
horário. A API precisa garantir que isso nunca aconteça, **inclusive sob requisições
simultâneas**, e aplicar as regras de uso das salas (R1–R5, R7) no servidor, nunca no cliente.

## Objetivo
> O que deve ser verdade quando essa spec estiver implementada?
> (1-3 frases, mensuráveis)

Um usuário autenticado cria uma reserva informando sala, início e fim. Nenhuma combinação de
requisições (sequenciais ou concorrentes) produz duas reservas ativas sobrepostas na mesma
sala nem mais de 3 reservas ativas futuras para o mesmo usuário.

## Atores
> Quem interage com essa funcionalidade?
> Ex: usuário autenticado, admin, sistema externo, cron job

- `user` e `admin` autenticados (a reserva é sempre criada em nome de quem está autenticado).

## Requisitos funcionais
> O que o sistema DEVE fazer. Use linguagem declarativa.
> - O sistema deve...
> - O usuário pode...
> - Quando X acontecer, Y deve ocorrer...

- O usuário pode criar uma reserva informando `room`, `start_at` e `end_at`.
- A reserva é criada com `status=active` e `user` = usuário autenticado.
- **R1** — O sistema não deve permitir duas reservas **ativas** sobrepostas na mesma sala.
  Intervalos são `[início, fim)`: 09:00–10:00 e 10:00–11:00 não conflitam.
- **R2** — O sistema não deve permitir reserva no passado: `start_at > agora`.
- **R3** — A duração deve estar entre 30 minutos e 4 horas, **inclusive** nos dois limites.
- **R4** — A reserva deve começar e terminar entre 07:00 e 20:00, no mesmo dia, no fuso
  `America/Sao_Paulo`. Terminar exatamente às 20:00 é permitido.
- **R5** — O usuário pode ter no máximo 3 reservas ativas futuras (`status=active` e
  `start_at > agora`). A 4ª deve ser recusada.
  **[DECISÃO]** Reserva em andamento (`start_at <= agora < end_at`) **não** conta como futura.
- **R7** — O sistema não deve permitir reserva em sala inativa.
- Reservas canceladas não contam para R1 nem para R5.
- **[DECISÃO]** Ordem das validações: payload (400) → sala ativa (R7) → janela de tempo
  (R2, R3, R4) → limite do usuário (R5) → sobreposição no INSERT (R1). A primeira violação
  encontrada é a devolvida.

## Requisitos não funcionais
> Performance, segurança, limites, restrições técnicas.
> Ex: resposta < 200ms, apenas usuários com role admin, max 100 itens por página

- **Concorrência R1** — garantida pelo banco: `ExclusionConstraint reservation_no_overlap`
  (`tstzrange(start_at, end_at, '[)') WITH &&`, `room WITH =`, `WHERE status='active'`).
  Verificar com `exists()` antes do INSERT **não** é suficiente (enunciado). O
  `IntegrityError` da constraint é traduzido em 409 fora da transação.
- **[DECISÃO] Lock na sala** — `select_for_update()` na sala no início da transação. Não
  garante a R1 (a constraint garante); evita o deadlock entre checagens concorrentes da
  ExclusionConstraint (que viraria 500 em vez de 409) e lê `is_active` com lock (R7).
- **Concorrência R5** — dentro de `transaction.atomic`, travar a linha do usuário com
  `select_for_update()` antes de contar as reservas.
- Ordem dos locks: sala → usuário (fixa, para não haver deadlock entre os locks).
- `CheckConstraint end_at > start_at` impede intervalos vazios que escapariam da exclusão.
- Regras R2–R4 são funções puras (`reservations/rules.py`) que recebem `now` por argumento.
- A estratégia de concorrência deve ser explicada no README, com as alternativas descartadas.

## Fluxo principal
> Passo a passo do caminho feliz, do ponto de entrada até o resultado esperado.
> 1. ...
> 2. ...

1. Usuário envia `POST /api/reservations` com `room`, `start_at`, `end_at`.
2. Serializer valida formato e tipos (400 se inválido; sala inexistente também é 400).
3. View chama `services.create_reservation(user=..., room=..., start_at=..., end_at=...)`.
4. Service abre a transação, trava a sala e verifica R7, chama `rules.validate_time_window` (R2–R4).
5. Service trava o usuário (`select_for_update`) e conta reservas ativas futuras (R5).
6. Service insere a reserva; o banco aplica R1.
7. Commit; API responde 201 com a reserva.

## Edge cases
> Situações limite que precisam de tratamento explícito.
> - O que acontece se [dado inválido]?
> - O que acontece se [recurso não existe]?
> - O que acontece se [usuário sem permissão]?

- Campo faltando ou data malformada → 400 `validation_error`.
- `room` inexistente → 400 `validation_error` (campo do payload, não recurso da URL).
- Data sem fuso → interpretada em `America/Sao_Paulo` (`TIME_ZONE` do Django).
- Data em outro fuso (ex.: `Z`) → convertida; R4 é avaliada em `America/Sao_Paulo`.
- `start_at == agora` → R2 (precisa ser estritamente futuro).
- `end_at <= start_at` → R3 (duração abaixo do mínimo).
- Duração 29 min → R3; 30 min → ok; 4 h → ok; 4 h 01 min → R3.
- Início 06:59 → R4; 07:00 → ok; fim 20:00 → ok; fim 20:01 → R4.
- Início 19:00 e fim 01:00 do dia seguinte → R4 (dias diferentes).
- Reserva adjacente (fim de uma = início da outra) → permitida.
- Mesmo horário em salas diferentes → permitido.
- Duas requisições simultâneas para o mesmo horário/sala → exatamente uma criada; a outra 409.
- Duas requisições simultâneas do mesmo usuário com 2 reservas futuras → exatamente uma criada; a outra 409.
- Sala desativada entre o GET e o POST → 422 `room_inactive`.

## Fora do escopo
> O que explicitamente NÃO será feito nessa spec.
> (evita scope creep e alinha expectativas)

- Admin criar reserva em nome de outro usuário.
- Editar reserva (alterar horário/sala); para mudar, cancela e cria outra.
- Reservas recorrentes, convidados, validação de capacidade vs. número de participantes.
- Lista de espera.

## Modelo de dados
> Tabelas/models envolvidos. Novos campos ou models necessários.
> Relacionamentos relevantes.

`reservations.Reservation`: `room` (FK `Room`, PROTECT), `user` (FK `User`, PROTECT),
`start_at`, `end_at` (timestamptz), `status` (`ReservationStatus`: `active` | `cancelled`),
`cancelled_at`, `created_at`.
Constraints: `reservation_end_after_start`, `reservation_no_overlap`.
Índices: `(user, status, start_at)` para R5; `(room, start_at)` para disponibilidade.

## Interface (se aplicável)
> Endpoints da API: método, rota, payload, resposta esperada.
> Ou: descrição da tela/componente se for frontend.

`POST /api/reservations` — autenticado.

```json
{"room": 1, "start_at": "2030-01-10T09:00:00-03:00", "end_at": "2030-01-10T10:00:00-03:00"}
```

Resposta 201: `{id, room, user, start_at, end_at, status, cancelled_at, created_at}`.

| Regra | HTTP | `error.code` |
|---|---|---|
| Payload inválido | 400 | `validation_error` |
| R1 sobreposição | 409 | `room_unavailable` |
| R2 passado | 422 | `start_in_past` |
| R3 duração | 422 | `invalid_duration` |
| R4 fora da janela | 422 | `outside_business_hours` |
| R5 limite | 409 | `reservation_limit_reached` |
| R7 sala inativa | 422 | `room_inactive` |

## Critérios de aceite
> Como validar que a implementação está correta?
> - Dado [contexto], quando [ação], então [resultado esperado]

- Dado uma sala ativa e horário válido, quando reservo, então recebo 201 e `status=active`.
- Dado uma reserva ativa 09–10, quando outro usuário reserva 09:30–11, então recebo 409 `room_unavailable`.
- Dado uma reserva ativa 09–10, quando reservo 10–11 na mesma sala, então recebo 201.
- Dado uma reserva cancelada 09–10, quando reservo 09–10, então recebo 201.
- Dado duas threads reservando o mesmo horário ao mesmo tempo, então só uma reserva existe no banco.
- Dado `start_at` no passado, quando reservo, então recebo 422 `start_in_past`.
- Dado duração de 29 min ou 4 h 01 min, quando reservo, então recebo 422 `invalid_duration`.
- Dado início 06:59 ou fim 20:01, quando reservo, então recebo 422 `outside_business_hours`.
- Dado 3 reservas ativas futuras, quando reservo a 4ª, então recebo 409 `reservation_limit_reached`.
- Dado 2 reservas ativas futuras e duas threads criando a 3ª e a 4ª ao mesmo tempo, então só uma é criada.
- Dado 3 reservas futuras sendo uma cancelada, quando reservo, então recebo 201.
- Dado uma sala inativa, quando reservo, então recebo 422 `room_inactive`.
