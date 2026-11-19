# Specs — Sala Livre

Specs (SDD) transcritas do enunciado do desafio (`docs/GW - Desafio Dev.pdf`, não versionado),
uma por funcionalidade. Itens marcados com **[DECISÃO]** resolvem ambiguidades do enunciado
e devem constar no README do projeto. Ambiguidades ainda sem decisão são marcadas com
**[PENDENTE]**.

| Spec | Funcionalidade | Regras |
|---|---|---|
| [01-autenticacao.md](01-autenticacao.md) | Cadastro, login, papéis | — |
| [02-salas.md](02-salas.md) | Gestão e listagem de salas | R7 (efeito da desativação) |
| [03-criar-reserva.md](03-criar-reserva.md) | Criação de reserva | R1, R2, R3, R4, R5, R7 |
| [04-listar-reservas.md](04-listar-reservas.md) | Listagem de reservas | — |
| [05-cancelar-reserva.md](05-cancelar-reserva.md) | Cancelamento de reserva | R6 |
| [06-disponibilidade.md](06-disponibilidade.md) | Intervalos livres de uma sala | R1, R4 (janela) |

## Regras de negócio (transcrição literal do enunciado)

> Todas devem ser garantidas pela API, e não pelo cliente.

| # | Regra |
|---|---|
| R1 | Duas reservas ativas não podem se sobrepor na mesma sala. |
| R2 | Não é possível reservar horário no passado. |
| R3 | A reserva deve durar no mínimo 30 minutos e no máximo 4 horas. |
| R4 | Só são permitidas reservas entre 07:00 e 20:00 (a reserva precisa começar e terminar dentro dessa janela, no mesmo dia). |
| R5 | Um usuário pode ter no máximo 3 reservas ativas no futuro ao mesmo tempo. |
| R6 | Uma reserva só pode ser cancelada com pelo menos 1 hora de antecedência do início. |
| R7 | Não se pode reservar uma sala inativa. |

> Sobre a R1: duas requisições simultâneas para o mesmo horário não podem resultar em duas
> reservas válidas. Verificar em memória antes do INSERT não é suficiente. Explicar no README
> a estratégia usada.

## Requisitos transversais (valem para todas as specs)

- Validação de entrada em todos os endpoints, com mensagens de erro claras.
- Formato de erro padronizado e códigos HTTP corretos:
  `{"error": {"code": "...", "message": "...", "details": {}}}`.

  | Situação | HTTP |
  |---|---|
  | Payload malformado / campo faltando | 400 `validation_error` |
  | Sem token / token inválido | 401 |
  | `user` em ação de admin | 403 |
  | Recurso inexistente ou de outro usuário | 404 (não revela existência) |
  | Conflito de estado (R1, R5) | 409 |
  | Regra de negócio violada (R2, R3, R4, R6, R7) | 422 |

- Listagens paginadas (`?page=&page_size=`, máx. 100 por página).
- Migrations versionadas; testes automatizados cobrindo R1 a R7.
- Datas sempre com fuso; banco em UTC; regras de horário avaliadas em `America/Sao_Paulo`.
