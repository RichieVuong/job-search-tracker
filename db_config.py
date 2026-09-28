import json
import os
from pathlib import Path

CONFIG_FILE = Path(__file__).with_name('.database-config.json')


def database_url():
    value = os.getenv('DATABASE_URL', '').strip()
    if value:
        return value
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())['DATABASE_URL']
    return ''
