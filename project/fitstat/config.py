"""Конфигурация клиента: clients/<slug>.toml."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLIENTS_DIR = ROOT / "clients"


@dataclass
class ClientConfig:
    slug: str
    name: str
    partner_channels: list[str]
    clubs: dict[int, dict] = field(default_factory=dict)

    def club(self, club_id: int) -> dict:
        """Настройки конкретного клуба (пустой словарь, если их нет)."""
        return self.clubs.get(club_id, {})


def load_config(slug: str, clients_dir: Path = CLIENTS_DIR) -> ClientConfig:
    with open(clients_dir / f"{slug}.toml", "rb") as f:
        raw = tomllib.load(f)
    clubs = {int(club_id): settings for club_id, settings in raw.get("clubs", {}).items()}
    return ClientConfig(
        slug=slug,
        name=raw["name"],
        partner_channels=raw["import"]["partner_channels"],
        clubs=clubs,
    )
