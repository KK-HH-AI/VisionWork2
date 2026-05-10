from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseTool(ABC):
    name: str
    description: str
    parameters_schema: Dict[str, Any]

    @abstractmethod
    async def execute(self, **kwargs) -> str:
        pass

    def to_tool_definition(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters_schema,
        }