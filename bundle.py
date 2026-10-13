import sys
import os

if getattr(sys, 'frozen', None):
    BUNDLED_DIR = sys._MEIPASS
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BUNDLED_DIR = os.path.dirname(os.path.abspath(__file__))
    BASE_DIR = BUNDLED_DIR

ASSETS_DIR = os.path.join(BASE_DIR, "assets")
STUB_DIR = os.path.join(BASE_DIR, "stub")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
VILLAGES_DIR = os.path.join(BASE_DIR, "villages")
QUESTS_DIR = os.path.join(VILLAGES_DIR, "quests")
CONFIG_DIR = os.path.join(BASE_DIR, "config")
CONFIG_PATCH_DIR = os.path.join(CONFIG_DIR, "patch")

MODS_DIR = os.path.join(BASE_DIR, "mods")
SAVES_DIR = os.path.join(BASE_DIR, "saves")


def resource_path(relative_path):
    """Devuelve la ruta absoluta de un recurso."""
    return os.path.join(BASE_DIR, relative_path)