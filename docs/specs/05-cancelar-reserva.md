# Spec: Cancelar reserva

## Contexto
> Por que essa funcionalidade existe? Qual problema resolve?
> Qual o impacto se não for feita?

Planos mudam e o horário precisa voltar a ficar livre para outras pessoas. Ao mesmo tempo,
cancelamentos em cima da hora prejudicam quem poderia ter usado a sala, e o histórico precisa
ser preservado para auditoria.

## Objetivo
> O que deve ser verdade quando essa spec estiver implementada?
> (1-3 frases, mensuráveis)

O dono da reserva (ou um admin) cancela uma reserva ativa com pelo menos 1 h de antecedência
do início (R6). O registro não é apagado: passa a `status=cancelled` com `cancelled_at`, e o
horário volta a ficar disponível.

## Atores
> Quem interage com essa funcionalidade?
> Ex: usuário autenticado, admin, sistema externo, cron job

- `user`: cancela apenas as próprias reservas.
- `admin`: cancela qualquer reserva.

## Requisitos funcionais
> O que o sistema DEVE fazer. Use linguagem declarativa.
> - O sistema deve...
> - O usuário pode...
> - Quando X acontecer, Y deve ocorrer...

- O `user` pode cancelar apenas reservas próprias.
- O `admin` pode cancelar reservas de qualquer usuário.
- O cancelamento não apaga o registro: define `status=cancelled` e `cancelled_at=agora`.
- **R6** — Só é possível cancelar se `start_at - agora >= 1 h` (exatamente 1 h é permitido).
- **[DECISÃO]** A R6 vale também para o `admin` (o enunciado não abre exceção).
- Após o cancelamento, o horário fica livre (R1 considera apenas reservas ativas) e a reserva
  deixa de contar para o limite da R5.

## Requisitos não funcionais
> Performance, segurança, limites, restrições técnicas.
> Ex: resposta < 200ms, apenas usuários com role admin, max 100 itens por página

- Reserva de outro usuário é tratada como inexistente para o `user` (404, não 403), para não
  revelar sua existência.
- R6 é uma função pura (`rules.validate_cancellation`) que recebe `now` por argumento.
- **[DECISÃO]** O cancelamento trava a linha da reserva (`select_for_update`) para que dois
  cancelamentos simultâneos não gerem estados inconsistentes.

## Fluxo principal
> Passo a passo do caminho feliz, do ponto de entrada até o resultado esperado.
> 1. ...
> 2. ...

1. Cliente envia `POST /api/reservations/{id}/cancel`.
2. API busca a reserva no escopo do usuário (todas, se admin; só as próprias, se user).
3. Service verifica que está ativa e aplica R6.
4. Service grava `status=cancelled` e `cancelled_at=agora`.
5. API responde 200 com a reserva atualizada.

## Edge cases
> Situações limite que precisam de tratamento explícito.
> - O que acontece se [dado inválido]?
> - O que acontece se [recurso não existe]?
> - O que acontece se [usuário sem permissão]?

- Reserva inexistente → 404.
- `user` cancelando reserva de outro → 404.
- Reserva já cancelada → **[DECISÃO]** 409 `reservation_not_active`.
- Faltam 59 min para o início → 422 `cancellation_too_late`.
- Falta exatamente 1 h → permitido.
- Reserva em andamento ou já encerrada → 422 `cancellation_too_late` (R6 cobre).
- Admin cancelando com menos de 1 h → 422 `cancellation_too_late`.

## Fora do escopo
> O que explicitamente NÃO será feito nessa spec.
> (evita scope creep e alinha expectativas)

- Exclusão física de reservas.
- Motivo do cancelamento, notificação ao dono quando o admin cancela.
- Reativar uma reserva cancelada.

## Modelo de dados
> Tabelas/models envolvidos. Novos campos ou models necessários.
> Relacionamentos relevantes.

`reservations.Reservation`: usa `status` (`ReservationStatus.CANCELLED`) e `cancelled_at`.
Sem novos campos.

## Interface (se aplicável)
> Endpoints da API: método, rota, payload, resposta esperada.
> Ou: descrição da tela/componente se for frontend.

`POST /api/reservations/{id}/cancel` — autenticado, sem payload.
Resposta 200: reserva com `status: "cancelled"` e `cancelled_at` preenchido.

| Situação | HTTP | `error.code` |
|---|---|---|
| Não existe / é de outro usuário | 404 | `not_found` |
| Já cancelada | 409 | `reservation_not_active` |
| R6 menos de 1 h | 422 | `cancellation_too_late` |

## Critérios de aceite
> Como validar que a implementação está correta?
> - Dado [contexto], quando [ação], então [resultado esperado]

- Dado minha reserva para daqui a 2 h, quando cancelo, então recebo 200, `status=cancelled` e `cancelled_at` preenchido.
- Dado uma reserva cancelada, quando consulto o banco, então o registro ainda existe.
- Dado minha reserva para daqui a 59 min, quando cancelo, então recebo 422 `cancellation_too_late`.
- Dado minha reserva para daqui a exatamente 1 h, quando cancelo, então recebo 200.
- Dado uma reserva de bruno, quando ana tenta cancelar, então recebe 404.
- Dado uma reserva de bruno, quando admin cancela com 2 h de antecedência, então recebe 200.
- Dado uma reserva já cancelada, quando cancelo de novo, então recebo 409.
- Dado uma reserva cancelada 09–10, quando outro usuário reserva 09–10, então recebe 201.
