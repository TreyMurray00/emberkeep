"""Generate local-only secrets without printing them. Never overwrite an existing .env."""
import secrets
from pathlib import Path
from cryptography.fernet import Fernet
root=Path(__file__).resolve().parents[1]
target=root/'.env'
if not target.exists():
    password=secrets.token_hex(24)
    target.write_text(f'POSTGRES_PASSWORD={password}\nDATABASE_URL=postgresql://emberkeep:{password}@127.0.0.1:55432/emberkeep\nADMIN_PASSWORD={secrets.token_urlsafe(24)}\nSECRET_KEY={Fernet.generate_key().decode()}\nAPP_ORIGIN=http://localhost:5173\n',encoding='utf-8')
    print('Created .env with unique local credentials. Read ADMIN_PASSWORD there to sign in.')
else: print('Existing .env preserved.')
