# NostraDa_Pick 1단계_DB설계명세서 (2026-02-26)

## 1. 개요
NostraDa_Pick (AI 기반 예언/투표 시뮬레이션 게임)의 핵심인 문제 관리, 유저 베팅 처리 등을 위해 Supabase (PostgreSQL) 상에 구축할 테이블 스키마 구조입니다.

## 2. 테이블 스키마 상세

### 2-1. `users` (사용자 테이블)
| 컬럼명 | 타입 | 제약조건 | 설명 |
|---|---|---|---|
| `id` | uuid | PK | Supabase auth.users 연동 혹은 내부 고유 ID |
| `email` | varchar | UNIQUE, NOT NULL | 사용자 이메일 (로그인 ID) |
| `points` | integer | DEFAULT 1000 | 초기 지급 기본 베팅 자산 |
| `created_at` | timestamp | DEFAULT now() | 가입 일자 |

### 2-2. `issues` (문제/이슈 테이블)
- Gemini가 생성한 예측 문제 정보 저장
| 컬럼명 | 타입 | 제약조건 | 설명 |
|---|---|---|---|
| `id` | uuid | PK | 문제 고유 ID |
| `title` | varchar | NOT NULL | "비트코인이 10만달러를 돌파할까?" 등 |
| `category` | varchar | NOT NULL | 'economy', 'sports', 'politics' 등 분류 |
| `status` | varchar | DEFAULT 'OPEN' | 상태 (OPEN, RESOLVING, RESOLVED, CANCELLED) |
| `close_at` | timestamp | NOT NULL | 베팅 마감 시간 |
| `resolved_at` | timestamp | NULL | 결과 확정 시간 |
| `correct_option_id`| uuid | NULL, FK(options.id) | 정답으로 판정된 선택지 ID |
| `created_at` | timestamp | DEFAULT now() | 문제 생성 일자 |

### 2-3. `options` (선택지 테이블)
| 컬럼명 | 타입 | 제약조건 | 설명 |
|---|---|---|---|
| `id` | uuid | PK | 선택지 고유 ID |
| `issue_id` | uuid | FK(issues.id) ON DELETE CASCADE | 어느 문제의 선택지인지 |
| `title` | varchar | NOT NULL | "네 돌파합니다", "아니오 돌파못합니다" 등 |
| `pool_amount` | integer | DEFAULT 0 | 이 선택지에 걸린 총 베팅 금액 합계 |

### 2-4. `bets` (베팅 내역 테이블)
| 컬럼명 | 타입 | 제약조건 | 설명 |
|---|---|---|---|
| `id` | uuid | PK | 베팅 고유 ID |
| `user_id` | uuid | FK(users.id) | 베팅한 유저 |
| `issue_id` | uuid | FK(issues.id) | 어떤 문제에 베팅했는지 |
| `option_id` | uuid | FK(options.id) | 어떤 선택지에 베팅했는지 |
| `amount` | integer | NOT NULL | 베팅한 포인트 량 |
| `status` | varchar | DEFAULT 'PENDING' | PENDING, WON(적중/정산완료), LOST(실패) |
| `created_at` | timestamp | DEFAULT now() | 베팅 시각 |

## 3. 적용 가이드
- 위 테이블들은 Supabase 프로젝트 대시보드의 SQL Editor에 쿼리를 실행하여 일괄 생성합니다.
- `options`의 `pool_amount`나 `users`의 `points`처럼 동시성 이슈가 있는 컬럼의 경우, 차후에 Supabase RPC(Stored Procedure)를 활용하여 정산 및 베팅 트랜잭션을 처리할 계획입니다.
