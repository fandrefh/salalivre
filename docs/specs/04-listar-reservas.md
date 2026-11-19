# Spec: Listar reservas

## Contexto
> Por que essa funcionalidade existe? Qual problema resolve?
> Qual o impacto se não for feita?

O usuário precisa ver o que reservou (para comparecer ou cancelar) e o admin precisa de uma
visão geral da ocupação, filtrando por sala, pessoa e período. Sem isso, a planilha volta a
ser a fonte de consulta.

## Objetivo
> O que deve ser verdade quando essa spec estiver implementada?
> (1-3 frases, mensuráveis)

`user` lista apenas as próprias reservas; `admin` lista as de todos, filtrando por sala,
usuário e intervalo de datas. Toda listagem é paginada.

## Atores
> Quem interage com essa funcionalidade?
> Ex: usuário autenticado, admin, sistema externo, cron job

- `user`: vê só as próprias reservas.
- `admin`: vê todas as reservas, com filtros.

## Requisitos funcionais
> O que o sistema DEVE fazer. Use linguagem declarativa.
> - O sistema deve...
> - O usuário pode...
> - Quando X acontecer, Y deve ocorrer...

- O `user` deve receber apenas reservas em que `user` = ele mesmo.
- O `admin` deve receber reservas de todos os usuários.
- O `admin` pode filtrar por `room`, `user`, `date_from` e `date_to`.
- A listagem inclui reservas ativas e canceladas, com `status` e `cancelled_at`.
- **[DECISÃO]** `date_from`/`date_to` são datas (`YYYY-MM-DD`), inclusivas, aplicadas sobre a
  data de `start_at` no fuso `America/Sao_Paulo`.
- **[DECISÃO]** Filtros enviados por `user` são ignorados (o escopo já é restrito a ele).

## Requisitos não funcionais
> Performance, segurança, limites, restrições técnicas.
> Ex: resposta < 200ms, apenas usuários com role admin, max 100 itens por página

- Paginação `?page=&page_size=` (padrão 20, máx. 100).
- Ordenação por `start_at`.
- Evitar N+1 (`select_related("room", "user")`).

## Fluxo principal
> Passo a passo do caminho feliz, do ponto de entrada até o resultado esperado.
> 1. ...
> 2. ...

1. Cliente envia `GET /api/reservations` (com filtros, se admin).
2. API restringe o queryset pelo papel do usuário.
3. API aplica filtros (admin), ordena e pagina.
4. Responde 200 com `count`, `next`, `previous`, `results`.

## Edge cases
> Situações limite que precisam de tratamento explícito.
> - O que acontece se [dado inválido]?
> - O que acontece se [recurso não existe]?
> - O que acontece se [usuário sem permissão]?

- `date_from` maior que `date_to` → lista vazia (não é erro).
- Data em formato inválido → 400 `validation_error`.
- Filtro por sala ou usuário inexistente → lista vazia.
- `page` além do total → 404 (padrão do DRF).
- `page_size` acima de 100 → limitado a 100.

## Fora do escopo
> O que explicitamente NÃO será feito nessa spec.
> (evita scope creep e alinha expectativas)

- Detalhe individual da reserva (`GET /api/reservations/{id}`).
- Filtro por status, busca textual, exportação.

## Modelo de dados
> Tabelas/models envolvidos. Novos campos ou models necessários.
> Relacionamentos relevantes.

`reservations.Reservation` (ver spec 03). Sem novos campos.

## Interface (se aplicável)
> Endpoints da API: método, rota, payload, resposta esperada.
> Ou: descrição da tela/componente se for frontend.

`GET /api/reservations?room=&user=&date_from=&date_to=&page=&page_size=`

```json
{
  "count": 1, "next": null, "previous": null,
  "results": [{"id": 1, "room": 1, "user": 2, "start_at": "...", "end_at": "...",
               "status": "active", "cancelled_at": null, "created_at": "..."}]
}
```

## Critérios de aceite
> Como validar que a implementação está correta?
> - Dado [contexto], quando [ação], então [resultado esperado]

- Dado reservas de ana e bruno, quando ana lista, então vê só as dela.
- Dado reservas de ana e bruno, quando admin lista, então vê ambas.
- Dado admin com `?room=1`, quando lista, então só vêm reservas da sala 1.
- Dado admin com `?user=2`, quando lista, então só vêm reservas do usuário 2.
- Dado admin com `?date_from=2030-01-10&date_to=2030-01-10`, então só vêm reservas desse dia.
- Dado 25 reservas, quando listo sem parâmetros, então recebo 20 e `next` preenchido.
