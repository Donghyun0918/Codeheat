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


@dataclass
class ContributorScore:
    """한 파일에 대한 기여자 한 명의 '도메인 지식 점수'."""

    name: str
    score: float  # Σ(최근성 가중치 × 변화량 가중치)
    commit_count: int
    last_commit_days: Optional[int] = None  # 마지막 커밋 이후 경과일

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "score": self.score,
            "commit_count": self.commit_count,
            "last_commit_days": self.last_commit_days,
        }


@dataclass
class FileOwnershipReport:
    """파일 한 개에 대한 오너십 분석 결과.

    blame(누가 쌌나)이 아니라 매칭(누가 해결할 수 있나)을 위한 점수다.
    복잡도가 급증한 시점에 커밋한 사람일수록 점수가 높다.
    """

    file: str
    total_commits: int
    top_contributors: list[ContributorScore] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "file": self.file,
            "total_commits": self.total_commits,
            "top_contributors": [c.to_dict() for c in self.top_contributors],
        }


@dataclass
class RefactorInsight:
    """3단계 LLM이 파일 한 개에 대해 내놓은 리팩토링 가이드.

    핵심: "누가 쌌나"가 아니라 "누구에게 무엇을 물어보면 풀리나".
    LLM에는 숫자/메타데이터만 넘기므로 이 구조에도 코드 본문은 없다.
    """

    file: str
    risk: str  # "high" | "medium" | "low"
    reason: str  # 왜 우선순위가 높은지 (복잡도/TODO 나이/오너 부재 근거)
    ask_who: str  # 도메인 지식 보유자(오너십 점수 기반)
    ask_what: str  # 그 사람에게 물어볼 구체적 질문

    def to_dict(self) -> dict:
        return {
            "file": self.file,
            "risk": self.risk,
            "reason": self.reason,
            "ask_who": self.ask_who,
            "ask_what": self.ask_what,
        }
