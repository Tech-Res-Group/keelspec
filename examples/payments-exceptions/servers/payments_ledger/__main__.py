"""`python -m servers.payments_ledger` runs the TOOL-payments-ledger server on stdio."""
from .server import server

server.run()
