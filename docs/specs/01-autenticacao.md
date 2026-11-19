# Spec: Autenticação e usuários

## Contexto
> Por que essa funcionalidade existe? Qual problema resolve?
> Qual o impacto se não for feita?

Hoje as reservas ficam numa planilha compartilhada, sem identificação confiável de quem
reservou. Toda regra da API (reservas próprias, limite por usuário, permissões de admin)
depende de saber quem está fazendo a requisição. Sem autenticação, nenhuma regra de negócio
pode ser garantida.

## Objetivo
> O que deve ser verdade quando essa spec estiver implementada?
> (1-3 frases, mensuráveis)

Qualquer pessoa pode se cadastrar como `user` e obter um token JWT com usuário e senha.
Senhas são armazenadas apenas como hash Argon2. Todo endpoint (exceto cadastro, login,
refresh, health e docs) exige token válido.

## Atores
> Quem interage com essa funcionalidade?
> Ex: usuário autenticado, admin, sistema externo, cron job

- Visitante (não autenticado): cadastra-se e faz login.
- `user` e `admin` autenticados: renovam o token.

## Requisitos funcionais
> O que o sistema DEVE fazer. Use linguagem declarativa.
> - O sistema deve...
> - O usuário pode...
> - Quando X acontecer, Y deve ocorrer...

- O visitante pode se cadastrar informando `username`, `email` e `password`.
- O cadastro deve sempre criar o usuário com `role=user`, ignorando qualquer `role` enviado.
- O usuário pode fazer login com `username` e `password` e receber `access` e `refresh` (JWT).
- O usuário pode renovar o `access` com um `refresh` válido.
- O sistema deve suportar dois papéis: `user` e `admin`.
- **[DECISÃO]** Um `admin` não é criado pela API: vem do seed, do `createsuperuser` ou do
  Django Admin. Evita escalada de privilégio pelo endpoint público.

## Requisitos não funcionais
> Performance, segurança, limites, restrições técnicas.
> Ex: resposta < 200ms, apenas usuários com role admin, max 100 itens por página

- Senha armazenada com hash Argon2 (enunciado: "bcrypt, argon2 ou similar").
- Senha validada pelos validadores padrão do Django (tamanho mínimo, senha comum, numérica,
  similar ao usuário).
- `access` expira em 30 min; `refresh` em 1 dia.
- (Bônus) Rate limit no login: escopo `login`, padrão `5/min` (`LOGIN_THROTTLE_RATE`).
- A senha nunca aparece em respostas nem em logs.

## Fluxo principal
> Passo a passo do caminho feliz, do ponto de entrada até o resultado esperado.
> 1. ...
> 2. ...

1. Visitante envia `POST /api/auth/register` com username, e-mail e senha.
2. API valida os dados, cria o usuário com `role=user` e responde 201 (sem a senha).
3. Visitante envia `POST /api/auth/login` com username e senha.
4. API responde 200 com `access` e `refresh`.
5. Cliente usa `Authorization: Bearer <access>` nas demais requisições.
6. Quando o `access` expira, cliente chama `POST /api/auth/refresh`.

## Edge cases
> Situações limite que precisam de tratamento explícito.
> - O que acontece se [dado inválido]?
> - O que acontece se [recurso não existe]?
> - O que acontece se [usuário sem permissão]?

- `username` ou `email` já existentes → 400 `validation_error` com o campo em `details`.
- Senha fraca → 400 `validation_error`.
- Payload com `role=admin` no cadastro → ignorado; usuário criado como `user`.
- Credenciais inválidas no login → 401, sem indicar se o usuário existe.
- Excesso de tentativas de login → 429.
- Token ausente, expirado ou inválido em endpoint protegido → 401.

## Fora do escopo
> O que explicitamente NÃO será feito nessa spec.
> (evita scope creep e alinha expectativas)

- Recuperação/troca de senha, confirmação de e-mail.
- Logout com blacklist de tokens.
- Gestão de usuários pela API (promover a admin, desativar usuário).

## Modelo de dados
> Tabelas/models envolvidos. Novos campos ou models necessários.
> Relacionamentos relevantes.

`accounts.User` (estende `AbstractUser`):
- `email` único.
- `role`: `UserRole` (`user` | `admin`), padrão `user`.
- Propriedade `is_admin_role`.

## Interface (se aplicável)
> Endpoints da API: método, rota, payload, resposta esperada.
> Ou: descrição da tela/componente se for frontend.

| Método | Rota | Auth | Payload | Resposta |
|---|---|---|---|---|
| POST | `/api/auth/register` | não | `{username, email, password}` | 201 `{id, username, email, role}` |
| POST | `/api/auth/login` | não | `{username, password}` | 200 `{access, refresh}` |
| POST | `/api/auth/refresh` | não | `{refresh}` | 200 `{access}` |

## Critérios de aceite
> Como validar que a implementação está correta?
> - Dado [contexto], quando [ação], então [resultado esperado]

- Dado um payload válido, quando cadastro, então recebo 201 e o usuário tem `role=user`.
- Dado um payload com `role=admin`, quando cadastro, então o usuário é criado como `user`.
- Dado um username já usado, quando cadastro, então recebo 400 `validation_error`.
- Dado um usuário cadastrado, quando faço login com a senha correta, então recebo `access` e `refresh`.
- Dado uma senha errada, quando faço login, então recebo 401.
- Dado um usuário criado, quando consulto o banco, então a senha está em hash Argon2.
- Dado nenhum token, quando acesso `GET /api/rooms`, então recebo 401.
