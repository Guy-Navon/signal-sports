"""Operational tooling (backups, verification, dev snapshots). Standard library
only, and nothing here imports the app's engine: these functions take explicit
file paths, so they can never act on whatever DATABASE_URL happens to say."""
