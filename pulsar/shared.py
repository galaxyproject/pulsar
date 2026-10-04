"""Values shared by Pulsar's client, its server, and Galaxy.

Must not import pulsar.client or pulsar.managers - Galaxy imports this without
wanting the rest of Pulsar loaded.
"""

COMMAND_VERSION_FILENAME = "COMMAND_VERSION"
