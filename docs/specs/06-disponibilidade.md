# Spec: Disponibilidade da sala

## Contexto
> Por que essa funcionalidade existe? Qual problema resolve?
> Qual o impacto se não for feita?

Sem saber o que está livre, o usuário reserva às cegas e recebe 409 por tentativa e erro.
Mostrar os intervalos livres do dia evita tentativas inválidas e substitui a consulta à
planilha.

## Objetivo
> O que deve ser verdade quando essa spec estiver implementada?
> (1-3 frases, mensuráveis)

Dado uma sala e um dia, a API devolve os intervalos livres dentro da janela 07:00–20:00
(`America/Sao_Paulo`), considerando apenas reservas ativas.

## Atores
> Quem interage com essa funcionalidade?
> Ex: usuário autenticado, admin, sistema externo, cron job

- `user` e `admin` autenticados.

## Requisitos funcionais
> O que o sistema DEVE fazer. Use linguagem declarativa.
> - O sistema deve...
> - O usuário pode...
> - Quando X acontecer, Y deve ocorrer...

- O usuário pode consultar a disponibilidade de uma sala informando um dia (`YYYY-MM-DD`).
- O sistema deve devolver os intervalos livres entre 07:00 e 20:00 daquele dia, no fuso
  `America/Sao_Paulo`.
- Apenas reservas com `status=active` ocupam horário; canceladas são ignoradas.
- Intervalos livres adjacentes ou contíguos são devolvidos já unidos (sem fragmentação).
- Dia sem reservas → um único intervalo 07:00–20:00.
- Dia totalmente ocupado → lista vazia.
- **[DECISÃO]** Sala inativa → 422 `room_inactive`, coerente com a R7 (não há disponibilidade
  em sala que não aceita reserva).
- **[DECISÃO]** Para o dia de hoje, o que já passou não é devolvido: a janela começa em
  `max(07:00, agora)`, para não sugerir horários que a R2 recusaria. Dia passado (ou hoje após
  20:00) → lista vazia.

## Requisitos não funcionais
> Performance, segurança, limites, restrições técnicas.
> Ex: resposta < 200ms, apenas usuários com role admin, max 100 itens por página

- O cálculo é uma função pura (`reservations/availability.py`): recebe a janela do dia e os
  intervalos ocupados; não acessa banco nem relógio. O recorte pelo "agora" é feito por quem
  chama, ajustando o início da janela; a assinatura de `free_intervals` não muda.
- Uma única query por requisição, usando o índice `(room, start_at)`.
- Não paginado (no máximo algumas dezenas de intervalos por dia).
- (Bônus, fora do escopo agora) Cache por sala+dia com invalidação ao criar/cancelar reserva.

## Fluxo principal
> Passo a passo do caminho feliz, do ponto de entrada até o resultado esperado.
> 1. ...
> 2. ...

1. Cliente envia `GET /api/rooms/{id}/availability?date=2030-01-10`.
2. API valida o parâmetro `date` e busca a sala (404 se não existir; 422 se inativa).
3. API monta a janela do dia (`max(07:00, agora)`–20:00 local) e busca as reservas ativas que
   a intersectam, ordenadas por início.
4. `availability.free_intervals` calcula os intervalos livres.
5. API responde 200 com a lista.

## Edge cases
> Situações limite que precisam de tratamento explícito.
> - O que acontece se [dado inválido]?
> - O que acontece se [recurso não existe]?
> - O que acontece se [usuário sem permissão]?

- `date` ausente ou malformado → 400 `validation_error`.
- Sala inexistente → 404.
- Sala inativa → 422 `room_inactive`.
- Hoje às 10:30, sem reservas → `[10:30–20:00]`.
- Hoje às 10:30, reserva 09–11 → `[11:00–20:00]` (a reserva em andamento ainda ocupa).
- Hoje após 20:00, ou dia passado → `[]`.
- Reserva 07:00–09:00 → primeiro intervalo livre começa às 09:00.
- Reserva 18:00–20:00 → último intervalo livre termina às 18:00.
- Reservas adjacentes 09–10 e 10–11 → nenhum intervalo de largura zero entre elas.
- Dia de virada de horário de verão → janela calculada com `zoneinfo`, sem assumir 24 h fixas.
- Intervalos livres menores que 30 min → devolvidos assim mesmo (é informação de ocupação;
  a R3 é aplicada na criação).

## Fora do escopo
> O que explicitamente NÃO será feito nessa spec.
> (evita scope creep e alinha expectativas)

- Disponibilidade de várias salas ou vários dias numa mesma chamada.
- Busca de "próximo horário livre" ou sugestão de salas.
- Cache (bônus).

## Modelo de dados
> Tabelas/models envolvidos. Novos campos ou models necessários.
> Relacionamentos relevantes.

Leitura de `rooms.Room` e `reservations.Reservation` (ativas). Sem novos campos.

## Interface (se aplicável)
> Endpoints da API: método, rota, payload, resposta esperada.
> Ou: descrição da tela/componente se for frontend.

`GET /api/rooms/{id}/availability?date=YYYY-MM-DD` — autenticado.

```json
{
  "room": 1,
  "date": "2030-01-10",
  "free": [
    {"start_at": "2030-01-10T07:00:00-03:00", "end_at": "2030-01-10T09:00:00-03:00"},
    {"start_at": "2030-01-10T10:00:00-03:00", "end_at": "2030-01-10T20:00:00-03:00"}
  ]
}
```

## Critérios de aceite
> Como validar que a implementação está correta?
> - Dado [contexto], quando [ação], então [resultado esperado]

- Dado uma sala sem reservas, quando consulto um dia futuro, então recebo `[07:00–20:00]`.
- Dado uma reserva ativa 09–10, quando consulto o dia, então recebo `[07–09, 10–20]`.
- Dado uma reserva cancelada 09–10, quando consulto o dia, então recebo `[07–20]`.
- Dado reservas 09–10 e 10–11, quando consulto, então recebo `[07–09, 11–20]`.
- Dado reservas cobrindo 07–20, quando consulto, então recebo `[]`.
- Dado uma sala inexistente, quando consulto, então recebo 404.
- Dado uma sala inativa, quando consulto, então recebo 422 `room_inactive`.
- Dado "agora" = hoje 10:30 e nenhuma reserva, quando consulto hoje, então recebo `[10:30–20:00]`.
- Dado um dia passado, quando consulto, então recebo `[]`.
- Dado `date=10/01/2030`, quando consulto, então recebo 400 `validation_error`.
