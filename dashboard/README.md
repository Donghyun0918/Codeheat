# CodeHeat 대시보드 🔥

CodeHeat CLI가 내보낸 리포트(JSON)를 **D3 트리맵 히트맵**으로 보여주는 정적 웹 대시보드. 4단계(출력 레이어)의 4-1.

- **면적 = 파일 크기(LOC)**, **색 = 복잡도 온도(max CCN)** — 빨갈수록 뜨겁다(리팩토링 부담 큼).
- 파일을 클릭하면 복잡도·TODO·**도메인 지식 보유자(오너십)**·LLM 인사이트(위험도/누구에게 무엇을)를 옆 패널에 표시.
- 핵심 철학 그대로: 책임 추궁(blame)이 아니라 **"누가 해결할 수 있나(매칭)"**.

## 스택

- Next.js 15 (App Router) + React 19, TypeScript
- D3는 `d3-hierarchy`(트리맵 레이아웃 계산)만 사용 — 렌더는 React가 SVG로. D3가 DOM을 직접 건드리지 않는다.
- **백엔드 없음**: `output: "export"` 정적 빌드. 데이터는 전부 브라우저에서만 처리된다(코드/리포트가 서버로 가지 않음).

## 실행

```bash
cd dashboard
npm install
npm run dev      # http://localhost:3000 개발 서버
# 또는 정적 빌드:
npm run build    # out/ 에 정적 사이트 생성 (Vercel/GitHub Pages 등 어디든 배포)
```

## 데이터 넣는 법

- **번들 샘플**: 열자마자 이 레포(codeheat)를 `scan + own` 한 결과가 보인다(`app/sample-data/`).
- **업로드**: 상단 드롭존에 CLI가 만든 JSON을 끌어다 놓으면 교체된다. 형식은 모양으로 자동 판별한다.
  - `smell_report.json` — 복잡도/TODO (트리맵의 기반, 필수)
  - `ownership_report.json` — 파일별 도메인 지식 보유자 (선택)
  - `insights_report.json` — LLM 위험도/질문 대상 (선택)

세 가지를 한 번에 끌어다 놓아도 되고, 파일 경로 기준으로 병합된다(경로가 안 맞으면 basename 폴백, CLI의 `load_and_merge`와 같은 규칙).

리포트 만드는 법:

```bash
codeheat scan <repo> --output smell_report.json
codeheat own <repo> --from-report smell_report.json --output ownership_report.json
codeheat insights smell_report.json --ownership-report ownership_report.json   # 선택(LLM)
```
