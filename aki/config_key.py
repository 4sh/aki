from dataclasses import dataclass


@dataclass(frozen=True)
class ConfigKey:
    key: str
    prefix: str = ''

    @property
    def path(self):
        return f'{self.prefix}.{self.key}' if self.prefix else self.key
