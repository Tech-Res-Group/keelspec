"""The governed-agent runtime (v2).

Modules here that need third-party packages (the router client, the MCP client,
telemetry) import them lazily and come with ``pip install 'keelspec[runtime]'``.
The policy engine and redaction are pure Python and work on the core install, so
``keelspec policy explain`` and the MCP ``product_policy_explain`` tool need nothing
extra.
"""
