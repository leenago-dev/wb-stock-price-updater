# stocks-name 관련 엔드포인트 구분 설명

## 핵심 정리

**두 가지 다른 엔드포인트가 있습니다:**

1. **POST /sync-stocks-name** → 데이터 수집 및 저장 (관리자용)
2. **GET /stocks-name/{symbol}** → 데이터 조회 (프론트엔드용)

---

## 1. POST /sync-stocks-name (데이터 수집)

### 역할
**FDR에서 종목 목록을 가져와서 Supabase에 저장하는 작업**

### 사용자
- **관리자** 또는 **Cloud Scheduler** (자동 실행)

### 인증
**필수** (Bearer Token)

### 동작
```
POST /sync-stocks-name
    ↓
FDR StockListing API 호출
    ↓
종목 목록 수집 (약 8,000개)
    ↓
Supabase stock_names 테이블에 저장
```

### 실행 주기
- **주 1회** 또는 **수동 실행**
- Cloud Scheduler로 자동화 가능

### 목적
- **데이터 최신화**: 신규 상장 종목 추가, 상장폐지 종목 비활성화
- **메타데이터 준비**: 프론트엔드에서 조회할 수 있도록 데이터 준비

---

## 2. GET /stocks-name/{symbol} (데이터 조회)

### 역할
**이미 저장된 종목 정보를 조회하는 작업**

### 사용자
- **프론트엔드** (사용자가 심볼 입력 시)
- **일반 사용자**

### 인증
**불필요** (공개 API)

### 동작
```
GET /stocks-name/AAPL
    ↓
Supabase stock_names 테이블에서 조회
    ↓
종목 정보 반환
```

### 실행 시점
- **사용자가 심볼을 입력할 때마다** (실시간)

### 목적
- **종목명 표시**: 사용자가 "AAPL" 입력 시 "Apple Inc." 표시
- **자동완성**: 종목 검색 기능 지원

---

## 전체 흐름도

```
┌─────────────────────────────────────────────────────────┐
│                    전체 데이터 흐름                      │
└─────────────────────────────────────────────────────────┘

[1단계: 데이터 수집 및 저장] (주 1회)
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│ Cloud        │─────▶│ POST         │─────▶│ FDR          │
│ Scheduler    │      │ /sync-stocks- │      │ StockListing  │
│ (주 1회)     │      │ name          │      │ API          │
└──────────────┘      └──────┬───────┘      └──────┬───────┘
                             │                     │
                             │ 종목 목록 수집      │
                             │                     │
                             ▼                     │
                      ┌──────────────┐            │
                      │ Supabase     │◀───────────┘
                      │ stock_names  │
                      │ 테이블 저장  │
                      └──────────────┘
                             │
                             │ (데이터 준비 완료)
                             │
[2단계: 데이터 조회] (사용자 요청 시마다)
                             │
                             ▼
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│ 사용자       │─────▶│ GET          │─────▶│ Supabase     │
│ (프론트엔드) │      │ /stocks-name │      │ stock_names  │
│              │      │ /{symbol}    │      │ 테이블 조회  │
└──────────────┘      └──────┬───────┘      └──────┬───────┘
                             │                     │
                             │ 종목 정보 반환      │
                             │                     │
                             ▼                     │
                      ┌──────────────┐            │
                      │ 프론트엔드   │◀───────────┘
                      │ 화면에 표시  │
                      └──────────────┘
```

---

## 역할 구분표

| 구분 | POST /sync-stocks-name | GET /stocks-name/{symbol} |
|------|----------------------|---------------------------|
| **역할** | 데이터 수집 및 저장 | 데이터 조회 |
| **사용자** | 관리자 / Cloud Scheduler | 프론트엔드 / 사용자 |
| **인증** | 필요 (Bearer Token) | 불필요 |
| **실행 주기** | 주 1회 (정기) | 사용자 요청 시마다 (실시간) |
| **데이터 소스** | FDR StockListing API | Supabase (이미 저장된 데이터) |
| **목적** | 최신 종목 목록 유지 | 종목명 표시 |

---

## 실제 사용 시나리오

### 시나리오 1: 주 1회 데이터 최신화 (관리자 작업)

```bash
# Cloud Scheduler 설정 (매주 월요일 오전 9시)
POST /sync-stocks-name
Authorization: Bearer YOUR_CRON_SECRET
Body: {}

→ FDR에서 최신 종목 목록 수집
→ Supabase에 저장
→ 신규 종목 추가, 상장폐지 종목 비활성화
```

**결과**: `stock_names` 테이블이 최신 상태로 유지됨

### 시나리오 2: 사용자가 심볼 입력 (프론트엔드)

```typescript
// 사용자가 "AAPL" 입력
const response = await fetch('https://api.example.com/stocks-name/AAPL');
const data = await response.json();
// → {"symbol": "AAPL", "name": "Apple Inc.", "country": "US"}

// 화면에 표시
displayStockName(data.name); // "Apple Inc."
```

**동작**:
```
GET /stocks-name/AAPL
    ↓
Supabase에서 조회 (이미 저장된 데이터)
    ↓
종목 정보 반환
```

---

## 혼동하기 쉬운 점

### ❌ 잘못된 이해

```
POST /sync-stocks-name가 프론트엔드에서도 사용되고
Cloud Run에서도 사용된다?
```

### ✅ 올바른 이해

```
1. POST /sync-stocks-name
   → 관리자/Cloud Scheduler가 주 1회 실행
   → 데이터 수집 및 저장

2. GET /stocks-name/{symbol}
   → 프론트엔드가 사용자 요청 시마다 호출
   → 데이터 조회
```

---

## 비유로 이해하기

### 도서관 비유

**POST /sync-stocks-name** = 도서관에 새 책을 입고하는 작업
- 주 1회 또는 필요할 때마다 실행
- 새로운 책을 가져와서 책장에 정리
- 관리자가 하는 작업

**GET /stocks-name/{symbol}** = 도서관에서 책을 찾는 작업
- 사용자가 책을 찾을 때마다 실행
- 이미 정리된 책장에서 책을 찾아서 제공
- 누구나 할 수 있는 작업

---

## 요약

### POST /sync-stocks-name
- **목적**: 데이터 수집 및 저장
- **사용자**: 관리자 / Cloud Scheduler
- **실행**: 주 1회 (정기)
- **인증**: 필요

### GET /stocks-name/{symbol}
- **목적**: 데이터 조회
- **사용자**: 프론트엔드 / 일반 사용자
- **실행**: 사용자 요청 시마다 (실시간)
- **인증**: 불필요

### 관계

```
POST /sync-stocks-name (데이터 준비)
    ↓
stock_names 테이블에 데이터 저장
    ↓
GET /stocks-name/{symbol} (데이터 사용)
    ↓
프론트엔드에서 종목명 표시
```

**결론**: 두 엔드포인트는 **서로 다른 역할**을 하며, **서로 보완**하는 관계입니다.
