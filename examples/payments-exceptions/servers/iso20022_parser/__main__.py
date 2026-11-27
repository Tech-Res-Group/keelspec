"""`python -m servers.iso20022_parser` runs the TOOL-iso20022-parser server on stdio."""
from .server import server

server.run()
