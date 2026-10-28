# ticket-manager

Monitor de tickets do RetroAchievements para os sets que eu registro.

## Instalação

```bash
pip install -r requirements.txt
cp .env.example .env   # e preencha os valores
python app.py
```

## Segurança (acesso por senha)

O app exige login com uma senha única. Configure no `.env`:

1. Gere uma chave de sessão:
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```
   e coloque em `SECRET_KEY`.
2. Gere o hash da sua senha:
   ```bash
   python -c "from werkzeug.security import generate_password_hash as g; print(g(input('Senha: ')))"
   ```
   e coloque em `APP_PASSWORD_HASH` **entre aspas simples** (o hash contém `$`).
3. Se o site estiver em HTTPS, use `COOKIE_SECURE=1`.

Sem senha configurada, o login fica bloqueado (o app não abre sem proteção).
Depois de 5 senhas erradas, o IP fica bloqueado por 5 minutos.

## Filtros

Na barra de monitoramento é possível filtrar por **status** (pendente, concluído,
em manutenção, não publicado), por **tag** (meus sets, em revisão) e ordenar a lista.
