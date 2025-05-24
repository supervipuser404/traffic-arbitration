import logging
from .config import config

logging.basicConfig(format='%(asctime)s %(process)d: %(levelname)s: %(message)s',
                    datefmt='[%Y-%m-%d %H:%M:%S]',
                    level=config.get('log', {}).get('level', 'INFO'))
logger = logging.getLogger()
