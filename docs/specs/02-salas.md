# Spec: Salas

## Contexto
> Por que essa funcionalidade existe? Qual problema resolve?
> Qual o impacto se não for feita?

As salas são o recurso disputado. Sem um cadastro centralizado, controlado pelo admin, não há
como saber o que pode ser reservado nem tirar uma sala de uso (reforma, manutenção) sem perder
o histórico de reservas.

## Objetivo
> O que deve ser verdade quando essa spec estiver implementada?
> (1-3 frases, mensuráveis)

`admin` cria, edita, lista e desativa salas; `user` apenas lista. Desativar uma sala impede
novas reservas (R7) sem afetar as já existentes, e nenhuma sala é apagada.

## Atores
> Quem interage com essa funcionalidade?
> Ex: usuário autenticado, admin, sistema externo, cron job

- `admin`: cria, edita, lista e desativa.
- `user`: lista.

## Requisitos funcionais
> O que o sistema DEVE fazer. Use linguagem declarativa.
> - O sistema deve...
> - O usuário pode...
> - Quando X acontecer, Y deve ocorrer...

- O `admin` pode criar uma sala com nome, capacidade, andar/localização e status.
- O `admin` pode editar qualquer campo da sala.
- O `admin` pode desativar uma sala (`is_active=false`) e reativá-la.
- Qualquer usuário autenticado pode listar salas (paginado).
- Quando uma sala é desativada, as reservas já existentes continuam válidas (não são
  canceladas nem alteradas).
- Sala inativa não aceita novas reservas (R7 — garantida na spec 03).
- **[DECISÃO]** O `user` vê apenas salas ativas na listagem (não há o que fazer com uma sala
  que não aceita reserva). O `admin` vê todas e pode filtrar com `?is_active=true|false`.

## Requisitos não funcionais
> Performance, segurança, limites, restrições técnicas.
> Ex: resposta < 200ms, apenas usuários com role admin, max 100 itens por página

- Escrita restrita a `role=admin` (`core.permissions.IsAdminOrReadOnly`).
- Nome único; capacidade > 0 garantida também no banco (`room_capacity_positive`).
- Listagem paginada, ordenada por nome.

## Fluxo principal
> Passo a passo do caminho feliz, do ponto de entrada até o resultado esperado.
> 1. ...
> 2. ...

1. `admin` envia `POST /api/rooms` com os dados da sala.
2. API valida e responde 201 com a sala criada.
3. Qualquer usuário autenticado consulta `GET /api/rooms` e vê a sala.
4. `admin` envia `PATCH /api/rooms/{id}` com `{"is_active": false}`.
5. A sala deixa de aceitar reservas; as existentes seguem ativas.

## Edge cases
> Situações limite que precisam de tratamento explícito.
> - O que acontece se [dado inválido]?
> - O que acontece se [recurso não existe]?
> - O que acontece se [usuário sem permissão]?

- `user` tenta criar ou editar sala → 403.
- Nome duplicado → 400 `validation_error`.
- Capacidade zero ou negativa → 400 `validation_error`.
- `PATCH` em sala inexistente → 404.
- Desativar sala com reservas futuras → permitido; reservas permanecem `active`.
- `DELETE` → 405 (não existe exclusão; desativar é o caminho).
- `user` envia `?is_active=false` → ignorado; continua vendo só salas ativas.

## Fora do escopo
> O que explicitamente NÃO será feito nessa spec.
> (evita scope creep e alinha expectativas)

- Exclusão física de salas.
- Recursos da sala (projetor, TV), fotos, horários de funcionamento por sala.
- Cancelamento automático das reservas ao desativar.

## Modelo de dados
> Tabelas/models envolvidos. Novos campos ou models necessários.
> Relacionamentos relevantes.

`rooms.Room`: `name` (único), `capacity` (> 0), `location`, `is_active` (padrão `true`),
`created_at`, `updated_at`. Relacionada a `Reservation` com `on_delete=PROTECT`.

## Interface (se aplicável)
> Endpoints da API: método, rota, payload, resposta esperada.
> Ou: descrição da tela/componente se for frontend.

| Método | Rota | Permissão | Payload | Resposta |
|---|---|---|---|---|
| GET | `/api/rooms` | autenticado (user: só ativas; admin: todas, `?is_active=`) | — | 200 paginado `[{id, name, capacity, location, is_active}]` |
| POST | `/api/rooms` | admin | `{name, capacity, location, is_active?}` | 201 sala |
| PATCH | `/api/rooms/{id}` | admin | campos parciais | 200 sala |

## Critérios de aceite
> Como validar que a implementação está correta?
> - Dado [contexto], quando [ação], então [resultado esperado]

- Dado um admin, quando crio uma sala válida, então recebo 201.
- Dado um user, quando tento criar uma sala, então recebo 403.
- Dado um user, quando listo salas, então recebo 200 paginado.
- Dado uma sala ativa e uma inativa, quando um user lista, então vê só a ativa.
- Dado uma sala ativa e uma inativa, quando o admin lista, então vê as duas.
- Dado admin com `?is_active=false`, quando lista, então vê só a inativa.
- Dado uma sala com reserva futura ativa, quando o admin a desativa, então a reserva continua `active`.
- Dado uma sala inativa, quando tento reservá-la, então recebo 422 `room_inactive` (spec 03).
