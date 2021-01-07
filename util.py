import dataclasses
from dataclasses import dataclass
from typing import Dict, Literal


@dataclass
class Color:
    red: float
    green: float
    blue: float

    @classmethod
    def from_hex(cls, hex: str) -> 'Color':
        return Color(*[int(hex[i:i+2], 16)/255 for i in range(0, 6, 2)])

    @classmethod
    def from_dict(cls, values: Dict[Literal['red', 'green', 'blue'], float]):
        return Color(**values)

    def to_hex(self) -> str:
        return '#' + ''.join(format(int(i * 255), '02x') for i in dataclasses.astuple(self))

    def to_dict(self) -> str:
        return dataclasses.asdict(self)
