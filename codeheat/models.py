"""CodeHeat 데이터 모델.

1단계 출력은 이후 LLM 레이어로 넘어간다. 그때 **코드 본문은 절대 넘기지 않고
숫자/메타데이터만** 넘기므로, 여기 dataclass들은 전부 직렬화 가능한
스칼라/리스트만 담는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TodoItem:
    """소스에서 발견한 TODO/FIXME 한 건."""

    line: int
    text: str
    age_days: Optional[int] = None  # git pickaxe 실패/생략 시 None

    def to_dict(self) -> dict:
        return {
            "line": self.line,
            "text": self.text,
            "age_days": self.age_days,
        }


@dataclass
class FileSmellReport:
    """파일 한 개에 대한 정적 분석 결과."""

    file: str
    complexity: int  # 파일 내 함수들의 최대 CCN
    avg_complexity: float
    function_count: int
    loc: int
    todos: list[TodoItem] = field(default_factory=list)
    duplication_ratio: float = 0.0  # 2단계(jscpd 등) 연동 전까지 비워둠

    @property
    def oldest_todo_days(self) -> Optional[int]:
        """todos 중 가장 오래된 TODO의 나이(일). 계산된 값이 없으면 None."""
        ages = [t.age_days for t in self.todos if t.age_days is not None]
        return max(ages) if ages else None

    def to_dict(self) -> dict:
        return {
            "file": self.file,
            "complexity": self.complexity,
            "avg_complexity": self.avg_complexity,
            "function_count": self.function_count,
            "loc": self.loc,
            "todos": [t.to_dict() for t in self.todos],
            "duplication_ratio": self.duplication_ratio,
            "oldest_todo_days": self.oldest_todo_days,
        }
