# CodeHeat for VS Code 🔥

코드 복잡도 히트맵을 에디터 안으로. CodeHeat CLI 리포트(JSON)를 읽어 **사이드바 트리뷰**와 **상태바**에 보여준다. 4단계(출력 레이어)의 4-3.

- **사이드바 히트맵**: 활동 막대의 🔥 아이콘 → 파일을 복잡도(온도) 내림차순으로. 핫파일일수록 빨간 불꽃 아이콘. 클릭하면 파일이 열리고, 호버하면 복잡도·오너·위험도·TODO가 뜬다.
- **상태바**: 현재 편집 중인 파일의 `🔥 CCN N · 오너` 표시. 클릭하면 히트맵 뷰로 점프.
- 철학 그대로: 책임 추궁(blame)이 아니라 **"누가 해결할 수 있나(매칭)"** — 오너는 단순 최다 수정자가 아니라 복잡도 급증 시점 기여자다.

## 데이터

워크스페이스 루트의 리포트 JSON을 읽는다(경로는 설정으로 변경 가능):

- `smell_report.json` — 복잡도/TODO (필수)
- `ownership_report.json` — 도메인 지식 보유자 (선택)
- `insights_report.json` — LLM 위험도/질문 대상 (선택)

리포트가 없으면 뷰에서 **워크스페이스 스캔** 버튼으로 만들 수 있다(아래 명령). 이때 `codeheat` CLI가 필요하다.

## 명령

| 명령 | 설명 |
| --- | --- |
| `CodeHeat: 워크스페이스 스캔 (scan + own)` | CLI로 `scan`+`own`을 돌려 리포트를 생성/갱신 |
| `CodeHeat: 리포트 새로고침` | 디스크의 리포트를 다시 읽음 |

## 설정

| 키 | 기본값 | 설명 |
| --- | --- | --- |
| `codeheat.smellReportPath` | `smell_report.json` | 복잡도 리포트 경로 |
| `codeheat.ownershipReportPath` | `ownership_report.json` | 오너십 리포트 경로 |
| `codeheat.insightsReportPath` | `insights_report.json` | 인사이트 리포트 경로 |
| `codeheat.cliCommand` | `codeheat` | CLI 실행 명령 (예: `python -m codeheat.cli`) |

## 개발

```bash
cd vscode-extension
npm install
npm run compile          # out/ 에 컴파일
# VS Code에서 이 폴더를 열고 F5 (Extension Development Host) 로 실행
```
