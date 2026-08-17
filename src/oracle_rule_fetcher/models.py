from dataclasses import dataclass, field


@dataclass
class Table:
    columns: list[str]
    rows: list[list] = field(default_factory=list)
