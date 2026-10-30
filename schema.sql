-- =============================================================================
-- 팀 편성 웹 앱 — Supabase(PostgreSQL) 스키마
--
-- 공고 5절 "DB 최소 참고안"을 따르고, 허용된 범위에서 열과 테이블을 늘렸습니다.
-- 모든 테이블 이름은 tf_ 로 시작합니다 (공고 4.2절, 6.3절 13번).
--
-- Supabase 대시보드 > SQL Editor 에 이 파일 전체를 붙여 넣고 실행하세요.
-- 여러 번 실행해도 안전합니다 (create ... if not exists).
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 역할 목록을 한 곳에서 관리하기 위한 도메인
-- 공고 2.2절의 6개 역할 밖의 값을 DB가 막습니다 (공고 5절).
-- -----------------------------------------------------------------------------
do $$
begin
    if not exists (select 1 from pg_type where typname = 'tf_role') then
        create domain tf_role as text
            check (value in (
                '기획자',
                '웹 프로그래머',
                '프론트엔드 디자이너',
                '테스터',
                '보고서 작성자',
                '발표자'
            ));
    end if;
end $$;


-- -----------------------------------------------------------------------------
-- tf_students : 학생과 관리자
--
-- main_role 은 관리자 계정에서만 null 입니다. 학생은 반드시 주 역할이 있습니다.
-- password_hash 에는 bcrypt 해시만 저장합니다. 평문 저장은 공고 6.3절 10번(-2점).
-- -----------------------------------------------------------------------------
create table if not exists tf_students (
    id            bigserial primary key,
    student_no    text    not null unique,
    name          text    not null,
    main_role     tf_role,
    password_hash text    not null,
    is_admin      boolean not null default false,

    -- 학생은 주 역할이 있어야 하고, 관리자는 주 역할이 없어야 합니다.
    constraint tf_students_main_role_required
        check ((is_admin and main_role is null) or (not is_admin and main_role is not null))
);


-- -----------------------------------------------------------------------------
-- tf_student_sub_roles : 보조 역할. 학생 1명에 0~2행 (공고 2.2절)
--
-- 기본 키가 (student_id, role) 이므로 같은 보조 역할이 두 번 들어가지 않습니다.
-- "최대 2개" 는 트리거로 DB에서 막습니다.
-- -----------------------------------------------------------------------------
create table if not exists tf_student_sub_roles (
    student_id bigint   not null references tf_students(id) on delete cascade,
    role       tf_role  not null,
    -- 명단 CSV 에 적힌 순서. 화면에 보조 역할을 CSV 와 같은 순서로 보여 주려고 둔다.
    position   smallint not null default 1,

    primary key (student_id, role)
);

create or replace function tf_check_sub_role_limit() returns trigger as $$
begin
    if (select count(*) from tf_student_sub_roles where student_id = new.student_id) > 2 then
        raise exception '보조 역할은 학생당 최대 2개입니다 (student_id=%)', new.student_id;
    end if;
    return null;
end $$ language plpgsql;

drop trigger if exists tf_sub_role_limit on tf_student_sub_roles;
create constraint trigger tf_sub_role_limit
    after insert on tf_student_sub_roles
    deferrable initially immediate
    for each row execute function tf_check_sub_role_limit();


-- -----------------------------------------------------------------------------
-- tf_teams : 팀
--
-- team_no 는 화면의 team_1, team_2 … 및 시나리오의 팀1, 팀2 와 같은 번호입니다
-- (공고 2.7절). 이름에서 번호를 뽑아내지 않고 열로 둡니다.
-- -----------------------------------------------------------------------------
create table if not exists tf_teams (
    id      bigserial primary key,
    team_no integer not null unique,
    name    text    not null unique,

    constraint tf_teams_team_no_positive check (team_no >= 1)
);


-- -----------------------------------------------------------------------------
-- tf_members : 팀원
--
-- 이 테이블의 두 제약이 공고 3장 표의 어려운 해결을 DB에서 보장합니다.
--   (team_id, slot_no) 기본 키 → "마지막 자리에 두 명이 동시에 들어감" 을 막아
--                                먼저 도착한 학생만 기록됩니다.
--   student_id 유일          → "한 학생은 한 팀에 소속" 을 지킵니다.
--   slot_no 1~4 검사          → 다섯 번째 자리를 막습니다 (공고 5절).
-- -----------------------------------------------------------------------------
create table if not exists tf_members (
    team_id    bigint   not null references tf_teams(id)    on delete cascade,
    slot_no    smallint not null,
    student_id bigint   not null unique references tf_students(id) on delete cascade,

    primary key (team_id, slot_no),

    constraint tf_members_slot_no_check check (slot_no between 1 and 4)
);

create index if not exists tf_members_team_id_idx on tf_members (team_id);


-- -----------------------------------------------------------------------------
-- tf_applications : 지원
--
-- 부분 유일 색인이 "결과가 나오기 전에는 다른 팀에 지원할 수 없음" 을 DB에서
-- 지켜 줍니다 (공고 2.4절). 거절·승인된 지원은 여러 건 남을 수 있습니다.
-- -----------------------------------------------------------------------------
create table if not exists tf_applications (
    id         bigserial   primary key,
    team_id    bigint      not null references tf_teams(id)    on delete cascade,
    student_id bigint      not null references tf_students(id) on delete cascade,
    status     text        not null,
    reason     text,
    created_at timestamptz not null default now(),

    constraint tf_applications_status_check check (status in ('대기', '승인', '거절'))
);

-- 한 학생에게 '대기' 상태의 지원은 최대 1건
create unique index if not exists tf_applications_one_pending_per_student
    on tf_applications (student_id)
    where status = '대기';

create index if not exists tf_applications_team_status_idx
    on tf_applications (team_id, status);


-- -----------------------------------------------------------------------------
-- tf_votes : 투표
--
-- (application_id, voter_id) 기본 키가 "한 번 투표하면 바꿀 수 없음" 을
-- 지켜 줍니다 (공고 2.4절).
-- -----------------------------------------------------------------------------
create table if not exists tf_votes (
    application_id bigint      not null references tf_applications(id) on delete cascade,
    voter_id       bigint      not null references tf_students(id)     on delete cascade,
    vote           text        not null,
    created_at     timestamptz not null default now(),

    primary key (application_id, voter_id),

    constraint tf_votes_vote_check check (vote in ('찬성', '거부'))
);


-- -----------------------------------------------------------------------------
-- tf_settings : 모집 마감 여부 등 앱 전역 상태
--
-- 쓰는 키
--   closed      '1' 이면 모집 마감됨 (공고 2.5절)
--   confirmed   '1' 이면 배정안이 확정되어 DB에 저장됨
--   team_count  관리자가 명단을 올릴 때 넣은 팀 수
-- -----------------------------------------------------------------------------
create table if not exists tf_settings (
    key   text primary key,
    value text
);


-- -----------------------------------------------------------------------------
-- tf_ai_logs : 오픈라우터 호출 기록 (공고 4.2절이 허용한 확장)
--
-- README.md 7.1절 5항의 "AI 모델 호출 실패 사례" 를 꾸며 내지 않고 실제 기록으로
-- 제시하기 위한 표입니다 (공고 6.3절 20번).
-- -----------------------------------------------------------------------------
create table if not exists tf_ai_logs (
    id         bigserial   primary key,
    attempt_no smallint    not null,
    model      text        not null,
    status     text        not null,
    detail     text,
    elapsed_ms integer,
    created_at timestamptz not null default now(),

    constraint tf_ai_logs_attempt_no_check check (attempt_no between 1 and 3),
    constraint tf_ai_logs_status_check
        check (status in ('성공', '시간초과', 'HTTP오류', '빈응답', '형식오류', '검사실패'))
);

create index if not exists tf_ai_logs_created_at_idx on tf_ai_logs (created_at desc);
