#!/usr/bin/env python3
"""Run as root during maintenance, after stopping API and ingestion."""
import logging
from pathlib import Path
import re
import subprocess
from urllib.parse import quote


def main():
    root = Path('/etc/cardboarddex')
    password = (root / 'next-password').read_text().strip()
    if not re.fullmatch('[a-f0-9]{64}', password):
        raise RuntimeError('Expected a generated 256-bit password')
    # Hex-only input is validated above. psql does not echo successful statements.
    subprocess.run(['docker', 'exec', '-i', 'cardboarddex-postgres', 'psql', '-U', 'cardboarddex',
                    '-d', 'cardboarddex', '-v', 'ON_ERROR_STOP=1'],
                   input=f"ALTER ROLE cardboarddex PASSWORD '{password}';\n", text=True, check=True)
    path = root / 'app.env'
    values = path.read_text().splitlines()
    replacements = {
        'POSTGRES_PASSWORD': password,
        'DATABASE_URL': f'postgresql+psycopg://cardboarddex:{quote(password, safe="")}@postgres:5432/cardboarddex',
    }
    result = [line for line in values if line.split('=', 1)[0] not in replacements]
    result.extend(f"{key}='{value}'" for key, value in replacements.items())
    path.write_text('\n'.join(result) + '\n')
    print('Database credential rotated; production configuration updated')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        logging.exception('Database password rotation failed; remain in maintenance')
        raise SystemExit(1)
