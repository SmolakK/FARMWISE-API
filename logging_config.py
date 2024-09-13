import logging

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S',
                    handlers=[
                        logging.FileHandler('server.log'),  # Log messages to a file
                        logging.StreamHandler()  # Also log messages to the console
                    ])

logger = logging.getLogger(__name__)
