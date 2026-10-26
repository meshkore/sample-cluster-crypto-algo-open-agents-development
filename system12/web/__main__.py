import sys

from ..config import SITE_DIR
from . import build_latest, cloudflare

site = build_latest()
print(f"built {SITE_DIR}", flush=True)
if "--deploy" in sys.argv:
    for url in cloudflare.deploy(site):
        print(f"deployed {url}", flush=True)
