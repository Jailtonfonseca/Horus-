import logging
import sys
from .config import LOG_FORMAT

def setup_logging(log_file: str):
    """Configura o logging para arquivo e console."""
    logging.basicConfig(
        level=logging.INFO,
        format=LOG_FORMAT,
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )
