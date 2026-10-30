# 팀 프로젝트 팀 편성 웹 앱

중간 과제 제출물. 학생이 스스로 팀을 편성하고, 남은 학생은 AI가 배정하되 앱이
규칙으로 검사하는 Streamlit 웹 앱이다.

작성자: **〈이름을 적으세요〉**

> **제출 전에 채워야 하는 곳이 `〈…〉` 로 표시되어 있습니다.** 1항(배포 주소)과
> 5~7항(사례)은 실제로 앱을 배포하고 돌려 본 결과여야 합니다. 공고 6.3절 20번은
> 사례를 꾸며 내면 시나리오 밖 점수를 0점으로 하므로, 비워 둔 채 제출하지 말고
> 직접 겪은 일을 적으세요. 아래 「사례를 채우는 방법」에 얻는 절차가 있습니다.

---

## 1. 배포 주소

〈https://…streamlit.app 을 적으세요〉

## 2. PRD와 구현 계획의 위치

| 문서 | 위치 |
| --- | --- |
| PRD | [`docs/PRD.md`](docs/PRD.md) |
| 구현 계획 | [`docs/구현 계획.md`](docs/구현%20계획.md) |

## 3. 고른 해결 방법

공고 3장 표의 7개 기능을 **모두 어려운 해결**로 만들었다.

| 기능 | 고른 것 | 어떻게 |
| --- | --- | --- |
| 다른 사람의 변경 보기 | 어려운 해결 | `st.fragment(run_every=5)` 로 바뀐 부분만 5초마다 다시 그림 ([`app/ui/student.py`](app/ui/student.py), [`app/ui/admin.py`](app/ui/admin.py)). 보험으로 `refresh` 단추도 함께 둠 |
| 필수 포함 역할을 지킬 수 없는 팀 | 어려운 해결 | 지원 단계에서 `남는자리 < 미충족` 이면 막음 ([`app/rules.py`](app/rules.py) `_structural_block`) |
| 같은 팀에 대기 중인 지원이 여럿 | 어려운 해결 | 승인 직전에 규칙을 다시 검사함. 처리 순서는 투표가 끝난 순서 ([`app/rules.py`](app/rules.py) `check_before_approval`, [`app/flow.py`](app/flow.py) `_try_approve`) |
| 마지막 자리에 두 명이 동시에 들어감 | 어려운 해결 | `tf_members` 의 `(team_id, slot_no)` 기본 키와 `student_id` 유일 제약으로 먼저 도착한 학생만 기록 ([`schema.sql`](schema.sql)) |
| AI 응답이 늦을 때 | 어려운 해결 | 모델마다 **전여** 120초를 재서 끊고 다음 모델로 넘어감 ([`app/ai.py`](app/ai.py) `_read_within_deadline`) |
| 3차 모델까지 실패 | 어려운 해결 | 2.5절 4항의 검사 다섯 가지를 모두 통과하는 배정을 완전탐색으로 끝까지 찾음 ([`app/flow.py`](app/flow.py) `solve_assignment`) |
| DB가 일시정지되지 않게 | 어려운 해결 | GitHub Actions 가 매일 DB 에 질의를 보냄 ([`.github/workflows/keepalive.yml`](.github/workflows/keepalive.yml)) |

### 필수 포함 역할 자리 계산

공고 3장의 설명을 다음 부등식으로 구현했다.

```
예상팀원 = 현재 팀원 ∪ {지원자}
남는자리 = 4 - |예상팀원|
충족수  = 예상팀원과 {기획자, 웹 프로그래머} 의 최대 매칭 크기
미충족  = 2 - 충족수

남는자리 < 미충족  →  막힘
```

부등식이어야 한다. 부록 2(중간) 8단계는 팀4가 학생11(RW) 혼자여서 충족수가 0인데
학생12가 지원하면 남는자리 2·미충족 2 이므로 막히지 **않아야** 하고(기대 결과:
대기), 부록 3(어려움) 11단계는 남는자리 1·미충족 2 이므로 막혀야 한다(기대 결과:
막힘). 두 단계가 서로를 검증하는 쌍이라, "필수 역할이 없으면 막는다" 로는 둘을
동시에 통과할 수 없다.

## 4. 쓴 모델 3개

| 차수 | 모델 |
| --- | --- |
| 1차 | `deepseek/deepseek-chat-v3-0324:free` |
| 2차 | `meta-llama/llama-3.3-70b-instruct:free` |
| 3차 | `qwen/qwen-2.5-72b-instruct:free` |

기본값은 [`app/ai.py`](app/ai.py) 의 `DEFAULT_MODELS` 이고, `.env` 의
`AI_MODEL_1/2/3` 으로 바꿀 수 있다. 무료 모델로 자동 연결하는 라우터
(`openrouter/free`)는 쓰지 않는다.

> **제출 전에 확인하세요.** 오픈라우터의 무료 모델 목록은 수시로 바뀝니다.
> <https://openrouter.ai/models?max_price=0> 에서 위 세 모델이 살아 있는지 보고,
> 없어졌으면 `.env` 와 이 표를 함께 고치세요.

## 5. 오픈라우터 AI 모델 호출 실패 사례

〈실제로 겪은 실패 1건 이상과 그 화면을 적으세요. 예: "1차 모델이 120초 안에
응답하지 않아 2차 모델로 넘어감(화면 `img/ai-timeout.png`)"〉

## 6. 클로드가 잘못된 추론이나 답변을 한 사례

〈실제로 겪은 사례 1건 이상과, 그것을 알아챈 방법을 화면이나 커밋을 근거로
적으세요. 예: "클로드가 만든 투표 코드가 팀원 1명의 찬성만으로 승인했음. 중간
시나리오 6단계를 해 보다 알아챘고, 커밋 a1b2c3d 에서 고침"〉

## 7. 본인이 제출한 앱에서 발견한 문제점이나 개선 필요 사항

〈실제로 발견한 문제 1건 이상과, 그 문제를 발견한 연습용 시나리오의 단계와 화면을
적으세요. "문제 없음" 은 인정되지 않습니다.〉

---

## 사례를 채우는 방법

5~7항은 사례만 적으면 부분 점수를 받고, 근거(화면, 커밋, 시나리오 단계)까지
적으면 점수를 다 받는다(공고 7.1절 8항). 아래 순서로 하면 근거가 저절로 모인다.

### 5항 — AI 호출 실패

이 앱은 오픈라우터 호출을 모두 `tf_ai_logs` 테이블에 남긴다. 관리자 화면의
「AI 배정 진행」(`assign_status`)에도 차수·모델·상태·소요 시간이 그대로 보인다.

1. 연습용 시나리오를 마감까지 진행하고 **AI 배정**을 누른다.
2. 무료 모델은 일곱 번 가운데 세 번쯤 실패하므로, 몇 번 돌리면 `시간초과`,
   `HTTP오류`(429), `빈응답`, `검사실패` 가운데 하나가 반드시 나온다.
3. 그 화면을 캡처해 `img/` 에 저장하고 5항에 파일 이름을 적는다.
4. 더 자세한 기록이 필요하면 Supabase SQL Editor 에서:
   ```sql
   select created_at, attempt_no, model, status, elapsed_ms, detail
   from tf_ai_logs order by created_at desc limit 20;
   ```

밤에 돌리면 무료 모델이 더 자주 실패한다(공고 4.3절).

### 6항 — 클로드의 잘못된 추론

앞으로 이 앱을 고치면서 클로드가 틀리는 일이 생기면 그때 적는 것이 가장 정확하다.
알아챈 근거로 쓸 수 있는 것은 두 가지다.

- **테스트**: `pytest` 가 잡아낸 실패. 어느 시나리오 몇 단계가 틀렸는지 테스트
  이름에 적혀 있다.
- **커밋**: `git log --oneline` 으로 고친 커밋의 해시를 찾아 적는다.

### 7항 — 발견한 문제점

아래 「연습용 시나리오 직접 해 보기」를 따라 세 시나리오를 손으로 돌려 보고,
기대 결과와 다른 단계나 불편한 점을 적는다. 화면이 몇 초 멈춘 것처럼 보이는 것도
개선 필요 사항이다.

---

## 처음 설정하기

### 1) 파이썬 환경

```bash
python -m venv .venv
```

```bash
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
```

### 2) Supabase

6장 실습에서 만든 프로젝트를 다시 쓴다. 새 프로젝트를 만들지 않는다(무료
프로젝트는 2개까지만 만들 수 있다).

DB 주소는 반드시 **풀러(Supavisor) 주소**를 쓴다. Streamlit Community Cloud 는
IPv4 로만 접속하는데, Supabase 무료 프로젝트의 직결 주소
(`db.xxx.supabase.co:5432`)는 IPv6 전용이어서 배포한 앱에서 연결이 안 된다.
Supabase 대시보드 > **Connect** > **Session pooler** 의 주소를 복사한다.

### 3) `.env`

[`.env.example`](.env.example) 을 복사해 `.env` 로 저장하고 값을 채운다.

```bash
cp .env.example .env
```

파일 이름은 정확히 `.env` 여야 한다. 편집기가 `.env.txt` 로 저장하면
`.gitignore` 가 걸러 내지 못해 키가 깃허브에 올라간다(공고 6.3절 7번, -3점).

### 4) 테이블 만들기

```bash
.venv/Scripts/python.exe scripts/apply_schema.py
```

Supabase 대시보드의 SQL Editor 에 [`schema.sql`](schema.sql) 을 붙여 넣어도 된다.
여러 번 실행해도 안전하다.

### 5) 로컬에서 돌려 보기

```bash
.venv/Scripts/python.exe -m streamlit run streamlit_app.py
```

### 6) 배포

1. 깃허브에 **비공개** 저장소로 올린다.
2. Streamlit 의 Workspace settings > Linked accounts 에서 Private access 옆
   **Connect here** 를 누른다.
3. 앱을 만들 때 Branch 는 `main`, Main file path 는 `streamlit_app.py` 로 한다.
4. Secrets 칸에 `.env` 와 같은 이름으로 넣는다.
   ```toml
   OPENROUTER_API_KEY = "sk-or-v1-..."
   DATABASE_URL = "postgresql://..."
   ADMIN_PASSWORD = "..."
   ```
5. 배포 뒤 앱의 Settings > Sharing 에서 "Who can view this app" 을
   **This app is public and searchable** 로 바꾸고 Save changes 를 누른다.
6. 로그인하지 않은 브라우저(시크릿 창)로 배포 주소를 열어 로그인 화면이 보이는지
   확인한다. 채점 프로그램은 로그인하지 않은 브라우저로 앱을 연다.

### 7) DB 일시정지 막기

깃허브 저장소 > Settings > Secrets and variables > Actions 에서 `DATABASE_URL`
이라는 이름으로 풀러 주소를 넣는다. 그러면
[`.github/workflows/keepalive.yml`](.github/workflows/keepalive.yml) 이 매일 DB 에
질의를 보낸다. Actions 탭에서 **Run workflow** 로 한 번 손수 돌려 성공하는지
확인한다.

---

## 테스트

```bash
.venv/Scripts/python.exe -m pytest -q
```

부록 연습용 시나리오 3개(쉬움 6단계, 중간 11단계, 어려움 15단계)의 **모든 단계**를
단계별로 재현해, 결과 안내의 첫 단어가 기대 결과와 같은지 확인한다. DB와 키가
없어도 돌아간다.

| 테스트 | 확인하는 것 |
| --- | --- |
| `test_rules.py` | 팀 규칙, 막힘 사유, 승인 직전 재검사, 확정 검사 |
| `test_scenarios.py` | 부록 시나리오 3개의 전 단계와 기대 결과 |
| `test_roster.py` | CSV 파싱. 나눠 준 세 파일과 손으로 적은 명단이 같은지 |
| `test_ai.py` | 모델 전환, 전여 120초 끊기, 응답 해석 |
| `test_assign.py` | AI 성공·실패와 자율 배정, 배정 불가 판정 |
| `test_auth.py` | 비밀번호 해시, 틀린 비밀번호 거부, 관리자 분리 |
| `test_keys.py` | 공고 2.7절 표의 key 와 글자까지 같은지 |
| `test_ui_wiring.py` | 화면이 그 key 들을 실제로 쓰는지, 겹치지 않는지 |
| `test_store_contract.py` | `PgStore` 와 인메모리 저장소가 같은 계약을 지키는지 |
| `test_postgres.py` | 실제 DB. 아래 환경 변수가 있을 때만 돈다 |

실제 Supabase 에 대고 확인하려면(tf_ 테이블 내용이 지워진다):

```bash
TEAM_FORMER_TEST_DB=1 .venv/Scripts/python.exe -m pytest tests/test_postgres.py -v
```

---

## 연습용 시나리오 직접 해 보기

명단은 [`fixtures/`](fixtures) 에 있다. 단계와 기대 결과는 공고 부록에 있다.

1. 브라우저를 열고 학번 `admin` 과 관리자 비밀번호로 로그인한다.
2. 「명단 올리기」에 `fixtures/쉬움.csv` 를 넣고 팀 수를 **3** 으로 하여
   **명단으로 처음 상태 만들기** 를 누른다.
3. 학생마다 **다른 브라우저 창**(또는 시크릿 창)으로 로그인한다. 같은 창에서
   로그아웃하며 번갈아 해도 되지만, 투표를 주고받을 때는 창을 따로 두는 쪽이 편하다.
   학생 비밀번호는 모두 `1234` 이다.
4. 부록의 단계를 위에서부터 그대로 하고, 「결과 안내」의 첫 단어가 기대 결과와
   같은지 본다.
5. 중간 시나리오는 팀 수 **4**, 어려움 시나리오도 팀 수 **4** 다.

---

## 구조

```
streamlit_app.py            진입점
app/
  rules.py                  팀 구성 규칙 (DB·화면 의존 없는 순수 함수)
  flow.py                   지원·투표·마감·배정 흐름
  assign.py                 AI 배정과 자율 배정의 조합
  ai.py                     오픈라우터 모델 체인
  auth.py                   로그인과 bcrypt 해시
  roster.py                 명단 CSV 파싱
  store.py                  저장소 계약
  repo.py                   Supabase 구현 (SQL 은 여기에만)
  db.py                     커넥션 풀
  config.py                 .env / Streamlit Secrets
  roles.py                  6개 역할
  ui/                       화면 (keys.py 에 공고 2.7절의 key)
schema.sql                  DDL
scripts/apply_schema.py     스키마 적용
scripts/keepalive.py        DB 깨우기
fixtures/                   연습용 명단 CSV 3개
tests/                      테스트
docs/                       PRD, 구현 계획
```

규칙이 DB와 화면을 모르는 순수 함수라서, Supabase와 오픈라우터 키 없이도 부록
시나리오 전 단계를 테스트로 확인할 수 있다. 자세한 설계 근거는
[`docs/구현 계획.md`](docs/구현%20계획.md) 에 있다.

## 비밀 값

오픈라우터 키, DB 주소, 관리자 비밀번호는 `.env`(로컬)와 Streamlit
Secrets(배포)에만 둔다. 코드에 적지 않고 화면과 로그에 출력하지 않는다. 있는지
확인할 때는 `config.secret_status()` 가 "있음/없음" 만 돌려준다.
