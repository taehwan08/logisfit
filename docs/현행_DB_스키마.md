# 현행 DB 스키마

> 분석일: 2026-03-04
> Django 4.2.27 / PostgreSQL (프로덕션) / SQLite (개발)

---

## 1. 마이그레이션 현황

### accounts (4건)
| # | 파일 | 날짜 | 주요 변경 |
|---|------|------|-----------|
| 0001 | initial | 2026-01-27 | User 모델 생성 |
| 0002 | user_clients | 2026-02-19 | User ↔ Client M2M 추가 |
| 0003 | passwordresetcode | (수동) | PasswordResetCode 모델 생성 |
| 0004 | user_session_key | (수동) | User.session_key 필드 추가 |

### clients (3건)
| # | 파일 | 날짜 | 주요 변경 |
|---|------|------|-----------|
| 0001 | initial | 2026-01-29 | Client, PriceContract 생성 |
| 0002 | (alter) | 2026-01-29 | PriceContract에 item_name, quantity, remarks, sub_category 추가; UK 변경 |
| 0003 | brand | 2026-02-19 | Brand 모델 생성 |

### inspection (2건)
| # | 파일 | 날짜 | 주요 변경 |
|---|------|------|-----------|
| 0001 | initial | 2026-02-10 | Order, OrderProduct, InspectionLog 생성 |
| 0002 | uploadbatch | 2026-02-11 | UploadBatch 생성; Order에 courier, delivery_memo, print_order, registered_date, upload_batch FK 추가 |

### inventory (13건)
| # | 파일 | 날짜 | 주요 변경 |
|---|------|------|-----------|
| 0001 | initial | 2026-02-18 | InventorySession, Location, InventoryRecord 생성 |
| 0002 | product | 2026-02-18 | Product 모델 생성 (barcode UNIQUE) |
| 0003 | product_display_name | 2026-02-18 | Product.display_name 추가 |
| 0004 | alter_product | 2026-02-18 | Product.barcode UNIQUE 제거 → unique_together=(barcode, name) |
| 0005 | record_fields | 2026-02-18 | InventoryRecord.expiry_date, lot_number 추가 |
| 0006 | inboundrecord | 2026-02-25 | InboundRecord 모델 생성 |
| 0007 | add_image | 2026-02-26 | InboundRecord.image (단일) 추가 |
| 0008 | inboundimage | (수동) | InboundImage 모델 생성 (다중 이미지) |
| 0009 | migrate_images | (수동) | 단일→다중 이미지 데이터 마이그레이션 |
| 0010 | remove_image | (수동) | InboundRecord.image 필드 제거 |
| 0011 | uppercase_barcode | (수동) | Location.barcode 대문자 변환 + 중복 병합 |
| 0012 | option_code | 2026-02-27 | Product.option_code 추가 |
| 0013 | client_brand | 2026-03-03 | Product.client FK, Product.brand FK 추가 |

### fulfillment (4건)
| # | 파일 | 날짜 | 주요 변경 |
|---|------|------|-----------|
| 0001 | initial | 2026-02-19 | FulfillmentOrder 생성 |
| 0002 | comment | 2026-02-19 | FulfillmentComment 생성 |
| 0003 | restructure | (수동) | brand FK, order_type, order_confirmed, sku_id, center, confirmed_quantity 추가; order_date DateField→CharField; receiving_date DateField→CharField; idx_fulfill_order_date 제거 |
| 0004 | platform_column | (수동) | PlatformColumnConfig 생성 |

---

## 2. 테이블별 상세 스키마

### 2-1. `accounts_user` (accounts.User)

| 컬럼 | DB 타입 | 제약 | 설명 |
|------|---------|------|------|
| id | BigAutoField | PK | |
| password | CharField(128) | NOT NULL | 해시된 비밀번호 |
| is_superuser | BooleanField | NOT NULL, default=False | |
| email | EmailField(254) | UNIQUE, NOT NULL | 로그인 식별자 |
| name | CharField(100) | NOT NULL | 이름 |
| phone | CharField(20) | blank | 연락처 |
| role | CharField(20) | NOT NULL, default='worker' | admin/client/worker |
| is_active | BooleanField | NOT NULL, default=True | |
| is_staff | BooleanField | NOT NULL, default=False | |
| is_approved | BooleanField | NOT NULL, default=False | |
| session_key | CharField(40) | NULL, blank | 동시 로그인 방지 |
| created_at | DateTimeField | auto_now_add | |
| updated_at | DateTimeField | auto_now | |
| last_login | DateTimeField | NULL, blank | |

**M2M**: `accounts_user_clients` → `clients.Client`
**M2M**: `accounts_user_groups` → `auth.Group`
**M2M**: `accounts_user_user_permissions` → `auth.Permission`

### 2-2. `accounts_password_reset_codes` (accounts.PasswordResetCode)

| 컬럼 | DB 타입 | 제약 | 설명 |
|------|---------|------|------|
| id | BigAutoField | PK | |
| user_id | BigInt | FK → accounts_user, CASCADE | |
| code | CharField(6) | NOT NULL | 6자리 인증번호 |
| is_used | BooleanField | NOT NULL, default=False | |
| attempt_count | IntegerField | NOT NULL, default=0 | |
| created_at | DateTimeField | auto_now_add | |
| expires_at | DateTimeField | NOT NULL | |

**인덱스**: `idx_reset_code_lookup` (user, is_used, expires_at)

### 2-3. `clients` (clients.Client)

| 컬럼 | DB 타입 | 제약 | 설명 |
|------|---------|------|------|
| id | BigAutoField | PK | |
| company_name | CharField(200) | NOT NULL | |
| business_number | CharField(12) | UNIQUE, NOT NULL | 사업자등록번호 |
| contact_person | CharField(100) | NOT NULL | |
| contact_phone | CharField(20) | NOT NULL | |
| contact_email | EmailField(254) | NOT NULL | |
| contract_start_date | DateField | NOT NULL, default=now | |
| contract_end_date | DateField | NULL, blank | |
| invoice_email | EmailField(254) | NOT NULL | |
| invoice_day | IntegerField | NOT NULL, default=1 | 1~28 |
| address | CharField(500) | blank | |
| address_detail | CharField(200) | blank | |
| memo | TextField | blank | |
| is_active | BooleanField | NOT NULL, default=True | |
| created_by_id | BigInt | FK → accounts_user, SET_NULL, NULL | |
| created_at | DateTimeField | auto_now_add | |
| updated_at | DateTimeField | auto_now | |

**인덱스**:
- `idx_client_company_name` (company_name)
- `idx_client_business_number` (business_number)
- `idx_client_is_active` (is_active)

### 2-4. `brands` (clients.Brand)

| 컬럼 | DB 타입 | 제약 | 설명 |
|------|---------|------|------|
| id | BigAutoField | PK | |
| client_id | BigInt | FK → clients, CASCADE | |
| name | CharField(200) | NOT NULL | |
| code | CharField(50) | blank | 내부 관리 코드 |
| is_active | BooleanField | NOT NULL, default=True | |
| memo | TextField | blank | |
| created_by_id | BigInt | FK → accounts_user, SET_NULL, NULL | |
| created_at | DateTimeField | auto_now_add | |
| updated_at | DateTimeField | auto_now | |

**제약**: `uq_brand_client_name` UNIQUE(client_id, name)

### 2-5. `price_contracts` (clients.PriceContract)

| 컬럼 | DB 타입 | 제약 | 설명 |
|------|---------|------|------|
| id | BigAutoField | PK | |
| client_id | BigInt | FK → clients, CASCADE | |
| work_type | CharField(30) | NOT NULL | WorkType choices (29종) |
| sub_category | CharField(100) | blank | |
| item_name | CharField(100) | blank | |
| unit_price | DecimalField(10,2) | NOT NULL, ≥0 | |
| unit | CharField(20) | NOT NULL, default='건' | |
| quantity | IntegerField | NOT NULL, default=1, ≥0 | |
| remarks | CharField(200) | blank | |
| valid_from | DateField | NOT NULL, default=now | |
| valid_to | DateField | NOT NULL | |
| memo | TextField | blank | |
| created_by_id | BigInt | FK → accounts_user, SET_NULL, NULL | |
| created_at | DateTimeField | auto_now_add | |

**인덱스**: `idx_price_contract_composite` (client, work_type, valid_from, valid_to)
**제약**: `uq_price_contract_client_type_item_from` UNIQUE(client, work_type, item_name, valid_from)

### 2-6. `products` (inventory.Product)

| 컬럼 | DB 타입 | 제약 | 설명 |
|------|---------|------|------|
| id | BigAutoField | PK | |
| barcode | CharField(50) | db_index | |
| name | CharField(200) | NOT NULL | |
| display_name | CharField(200) | blank, default='' | 관리명 |
| option_code | CharField(50) | db_index, blank, default='' | |
| client_id | BigInt | FK → clients, SET_NULL, NULL | |
| brand_id | BigInt | FK → brands, SET_NULL, NULL | |
| created_at | DateTimeField | auto_now_add | |
| updated_at | DateTimeField | auto_now | |

**제약**: `unique_together` (barcode, name)

### 2-7. `locations` (inventory.Location)

| 컬럼 | DB 타입 | 제약 | 설명 |
|------|---------|------|------|
| id | BigAutoField | PK | |
| barcode | CharField(50) | UNIQUE, db_index | 대문자 자동변환 |
| name | CharField(100) | blank, default='' | |
| zone | CharField(50) | blank, default='' | |
| created_at | DateTimeField | auto_now_add | |

### 2-8. `inventory_sessions` (inventory.InventorySession)

| 컬럼 | DB 타입 | 제약 | 설명 |
|------|---------|------|------|
| id | BigAutoField | PK | |
| name | CharField(100) | NOT NULL | |
| status | CharField(10) | NOT NULL, default='active' | active/closed |
| started_at | DateTimeField | auto_now_add | |
| ended_at | DateTimeField | NULL, blank | |
| started_by | CharField(50) | blank, default='' | |

### 2-9. `inventory_records` (inventory.InventoryRecord)

| 컬럼 | DB 타입 | 제약 | 설명 |
|------|---------|------|------|
| id | BigAutoField | PK | |
| session_id | BigInt | FK → inventory_sessions, CASCADE | |
| location_id | BigInt | FK → locations, CASCADE | |
| barcode | CharField(50) | db_index | 상품바코드 |
| product_name | CharField(200) | blank, default='' | |
| quantity | IntegerField | NOT NULL, default=1 | |
| expiry_date | CharField(20) | blank, default='' | |
| lot_number | CharField(50) | blank, default='' | |
| worker | CharField(50) | blank, default='' | |
| created_at | DateTimeField | auto_now_add | |

**인덱스**:
- `inventory_r_barcode_79c384_idx` (barcode)
- `inventory_r_session_a974d9_idx` (session, location)

### 2-10. `inbound_records` (inventory.InboundRecord)

| 컬럼 | DB 타입 | 제약 | 설명 |
|------|---------|------|------|
| id | BigAutoField | PK | |
| product_id | BigInt | FK → products, CASCADE | |
| quantity | IntegerField | NOT NULL | |
| expiry_date | CharField(20) | blank, default='' | |
| lot_number | CharField(50) | blank, default='' | |
| status | CharField(20) | NOT NULL, default='pending' | pending/completed |
| memo | TextField | blank, default='' | |
| registered_by_id | BigInt | FK → accounts_user, SET_NULL, NULL | |
| completed_by_id | BigInt | FK → accounts_user, SET_NULL, NULL | |
| completed_at | DateTimeField | NULL, blank | |
| created_at | DateTimeField | auto_now_add | |
| updated_at | DateTimeField | auto_now | |

### 2-11. `inbound_images` (inventory.InboundImage)

| 컬럼 | DB 타입 | 제약 | 설명 |
|------|---------|------|------|
| id | BigAutoField | PK | |
| inbound_record_id | BigInt | FK → inbound_records, CASCADE | |
| image | ImageField | NOT NULL | upload_to='inbound/%Y/%m/' |
| created_at | DateTimeField | auto_now_add | |

### 2-12. `upload_batches` (inspection.UploadBatch)

| 컬럼 | DB 타입 | 제약 | 설명 |
|------|---------|------|------|
| id | BigAutoField | PK | |
| file_name | CharField(200) | NOT NULL | |
| print_order | CharField(100) | blank, default='' | |
| delivery_memo | CharField(200) | blank, default='' | |
| total_orders | IntegerField | NOT NULL, default=0 | |
| total_products | IntegerField | NOT NULL, default=0 | |
| uploaded_at | DateTimeField | auto_now_add | |
| uploaded_by | CharField(50) | blank, default='' | |

### 2-13. `orders` (inspection.Order)

| 컬럼 | DB 타입 | 제약 | 설명 |
|------|---------|------|------|
| id | BigAutoField | PK | |
| upload_batch_id | BigInt | FK → upload_batches, CASCADE, NULL | |
| tracking_number | CharField(50) | UNIQUE, db_index | |
| seller | CharField(100) | NOT NULL | |
| receiver_name | CharField(100) | NOT NULL | |
| receiver_phone | CharField(20) | NOT NULL | |
| receiver_address | TextField | NOT NULL | |
| registered_date | CharField(50) | blank, default='' | |
| courier | CharField(50) | blank, default='' | |
| print_order | CharField(100) | blank, default='' | |
| delivery_memo | CharField(200) | blank, default='' | |
| status | CharField(20) | NOT NULL, default='대기중' | 대기중/검수중/완료 |
| uploaded_at | DateTimeField | auto_now_add | |
| completed_at | DateTimeField | NULL, blank | |

**인덱스**: `orders_status_762191_idx` (status)

### 2-14. `order_products` (inspection.OrderProduct)

| 컬럼 | DB 타입 | 제약 | 설명 |
|------|---------|------|------|
| id | BigAutoField | PK | |
| order_id | BigInt | FK → orders, CASCADE | |
| barcode | CharField(50) | db_index | |
| product_name | CharField(200) | NOT NULL | |
| quantity | IntegerField | NOT NULL | |
| scanned_quantity | IntegerField | NOT NULL, default=0 | |

**인덱스**: `order_produ_barcode_dc87a5_idx` (barcode)

### 2-15. `inspection_logs` (inspection.InspectionLog)

| 컬럼 | DB 타입 | 제약 | 설명 |
|------|---------|------|------|
| id | BigAutoField | PK | |
| tracking_number | CharField(50) | NOT NULL | |
| barcode | CharField(50) | NULL, blank | |
| scan_type | CharField(20) | NOT NULL | 송장/상품 |
| alert_code | CharField(20) | NOT NULL | 8종 |
| worker | CharField(50) | NULL, blank | |
| created_at | DateTimeField | auto_now_add | |

**인덱스**:
- `inspection__trackin_a758ee_idx` (tracking_number)
- `inspection__created_c7755b_idx` (created_at)

### 2-16. `fulfillment_orders` (fulfillment.FulfillmentOrder)

| 컬럼 | DB 타입 | 제약 | 설명 |
|------|---------|------|------|
| id | BigAutoField | PK | |
| client_id | BigInt | FK → clients, CASCADE | |
| brand_id | BigInt | FK → brands, SET_NULL, NULL | |
| platform | CharField(20) | NOT NULL | 7종 |
| status | CharField(20) | NOT NULL, default='pending' | 4단계 |
| order_number | CharField(100) | NOT NULL | |
| order_type | CharField(100) | blank | |
| order_confirmed | CharField(100) | blank | |
| sku_id | CharField(100) | blank | |
| product_name | CharField(300) | NOT NULL | |
| barcode | CharField(100) | blank | |
| center | CharField(100) | blank | |
| receiving_date | CharField(50) | blank | |
| order_date | CharField(50) | blank | |
| order_quantity | IntegerField | NOT NULL, default=0, ≥0 | |
| confirmed_quantity | IntegerField | NOT NULL, default=0, ≥0 | |
| manager | CharField(100) | blank | |
| expiry_date | CharField(50) | blank | |
| box_quantity | IntegerField | NOT NULL, default=0, ≥0 | |
| address | TextField | blank | |
| memo | TextField | blank | |
| platform_data | JSONField | NOT NULL, default={} | |
| confirmed_at | DateTimeField | NULL | |
| confirmed_by_id | BigInt | FK → accounts_user, SET_NULL, NULL | |
| shipped_at | DateTimeField | NULL | |
| shipped_by_id | BigInt | FK → accounts_user, SET_NULL, NULL | |
| synced_at | DateTimeField | NULL | |
| synced_by_id | BigInt | FK → accounts_user, SET_NULL, NULL | |
| created_by_id | BigInt | FK → accounts_user, SET_NULL, NULL | |
| created_at | DateTimeField | auto_now_add | |
| updated_at | DateTimeField | auto_now | |

**인덱스**:
- `idx_fulfill_client_platform` (client, platform)
- `idx_fulfill_status` (status)
- `idx_fulfill_order_number` (order_number)

### 2-17. `fulfillment_comments` (fulfillment.FulfillmentComment)

| 컬럼 | DB 타입 | 제약 | 설명 |
|------|---------|------|------|
| id | BigAutoField | PK | |
| order_id | BigInt | FK → fulfillment_orders, CASCADE | |
| author_id | BigInt | FK → accounts_user, SET_NULL, NULL | |
| content | TextField | NOT NULL | |
| is_system | BooleanField | NOT NULL, default=False | |
| created_at | DateTimeField | auto_now_add | |
| updated_at | DateTimeField | auto_now | |

### 2-18. `fulfillment_platform_column_configs` (fulfillment.PlatformColumnConfig)

| 컬럼 | DB 타입 | 제약 | 설명 |
|------|---------|------|------|
| id | BigAutoField | PK | |
| platform | CharField(20) | NOT NULL | 7종 |
| name | CharField(100) | NOT NULL | 표시명 |
| key | CharField(100) | NOT NULL | 저장키 |
| column_type | CharField(20) | NOT NULL, default='text' | text/number/date |
| display_order | IntegerField | NOT NULL, default=0 | |
| is_required | BooleanField | NOT NULL, default=False | |
| is_active | BooleanField | NOT NULL, default=True | |
| created_at | DateTimeField | auto_now_add | |
| updated_at | DateTimeField | auto_now | |

**인덱스**: `idx_platform_col_active` (platform, is_active)
**제약**: `uq_platform_column_key` UNIQUE(platform, key)

---

## 3. FK/M2M 관계도

```
┌─────────────────────────────────────────────────────────────────────┐
│                         accounts.User                               │
│  PK: id                                                             │
│  M2M: clients ──────────────────────┐                               │
│  M2M: groups → auth.Group           │                               │
│  M2M: user_permissions → auth.Perm  │                               │
└──┬──────┬──────┬──────┬─────────────┘                               │
   │      │      │      │                                             │
   │ (FK) │(FK)  │(FK)  │(FK)                                        │
   │      │      │      │                                             │
   │   ┌──┘   ┌──┘   ┌──┘                                            │
   │   │      │      │                                                │
   ▼   ▼      ▼      ▼                                                │
┌──────────────────────────┐    ┌─────────────────────────┐           │
│ accounts.PasswordReset   │    │     clients.Client      │ ◄─────────┘
│ Code                     │    │  PK: id                 │    (M2M)
│ FK: user → User          │    │  FK: created_by → User  │
└──────────────────────────┘    └──┬──────────┬───────────┘
                                   │          │
                          (FK)     │          │  (FK)
                                   ▼          ▼
                        ┌──────────────┐  ┌────────────────────────┐
                        │ clients.Brand│  │ clients.PriceContract  │
                        │ FK: client   │  │ FK: client → Client    │
                        │ FK: created_ │  │ FK: created_by → User  │
                        │    by → User │  └────────────────────────┘
                        └──┬───────────┘
                           │
           ┌───────────────┼────────────────────────────┐
           │               │                            │
           ▼               ▼                            ▼
┌──────────────────┐  ┌──────────────────────┐  ┌─────────────────────┐
│ inventory.Product│  │ fulfillment.         │  │ fulfillment.        │
│ FK: client       │  │ FulfillmentOrder     │  │ FulfillmentOrder    │
│    → Client      │  │ FK: client → Client  │  │ FK: brand → Brand   │
│ FK: brand        │  │ FK: brand → Brand    │  │                     │
│    → Brand       │  │ FK: confirmed_by     │  └─────────────────────┘
└──┬───────────────┘  │    → User            │
   │                  │ FK: shipped_by       │
   │ (FK)             │    → User            │
   ▼                  │ FK: synced_by → User │
┌──────────────────┐  │ FK: created_by→ User │
│ inventory.       │  └──┬───────────────────┘
│ InboundRecord    │     │
│ FK: product      │     │ (FK)
│    → Product     │     ▼
│ FK: registered_  │  ┌──────────────────────┐
│    by → User     │  │ fulfillment.         │
│ FK: completed_   │  │ FulfillmentComment   │
│    by → User     │  │ FK: order            │
└──┬───────────────┘  │    → FulfillmentOrder│
   │                  │ FK: author → User    │
   │ (FK)             └──────────────────────┘
   ▼
┌──────────────────┐
│ inventory.       │
│ InboundImage     │
│ FK: inbound_     │
│    record        │
│    → InboundRec  │
└──────────────────┘


┌──────────────────────┐     ┌──────────────────────┐
│ inventory.           │     │ inventory.            │
│ InventorySession     │     │ Location              │
│ PK: id               │     │ PK: id                │
└──┬───────────────────┘     └──┬───────────────────┘
   │                            │
   │ (FK)                       │ (FK)
   ▼                            ▼
┌──────────────────────────────────────┐
│ inventory.InventoryRecord            │
│ FK: session → InventorySession       │
│ FK: location → Location              │
└──────────────────────────────────────┘


┌──────────────────────┐
│ inspection.          │
│ UploadBatch          │
└──┬───────────────────┘
   │ (FK)
   ▼
┌──────────────────────┐     ┌──────────────────────┐
│ inspection.Order     │     │ inspection.           │
│ FK: upload_batch     │     │ InspectionLog         │
│    → UploadBatch     │     │ (독립 테이블 — FK 없음)│
└──┬───────────────────┘     └──────────────────────┘
   │ (FK)
   ▼
┌──────────────────────┐
│ inspection.          │
│ OrderProduct         │
│ FK: order → Order    │
└──────────────────────┘
```

---

## 4. FK 관계 요약표

| 소스 테이블 | 컬럼 | 대상 테이블 | ON DELETE | related_name |
|-------------|------|-------------|-----------|--------------|
| accounts_user | clients (M2M) | clients | — | users |
| accounts_password_reset_codes | user_id | accounts_user | CASCADE | password_reset_codes |
| clients | created_by_id | accounts_user | SET_NULL | created_clients |
| brands | client_id | clients | CASCADE | brands |
| brands | created_by_id | accounts_user | SET_NULL | created_brands |
| price_contracts | client_id | clients | CASCADE | price_contracts |
| price_contracts | created_by_id | accounts_user | SET_NULL | created_price_contracts |
| products | client_id | clients | SET_NULL | products |
| products | brand_id | brands | SET_NULL | products |
| inventory_records | session_id | inventory_sessions | CASCADE | records |
| inventory_records | location_id | locations | CASCADE | records |
| inbound_records | product_id | products | CASCADE | inbound_records |
| inbound_records | registered_by_id | accounts_user | SET_NULL | inbound_registered |
| inbound_records | completed_by_id | accounts_user | SET_NULL | inbound_completed |
| inbound_images | inbound_record_id | inbound_records | CASCADE | images |
| orders | upload_batch_id | upload_batches | CASCADE | orders |
| order_products | order_id | orders | CASCADE | products |
| fulfillment_orders | client_id | clients | CASCADE | fulfillment_orders |
| fulfillment_orders | brand_id | brands | SET_NULL | fulfillment_orders |
| fulfillment_orders | confirmed_by_id | accounts_user | SET_NULL | + |
| fulfillment_orders | shipped_by_id | accounts_user | SET_NULL | + |
| fulfillment_orders | synced_by_id | accounts_user | SET_NULL | + |
| fulfillment_orders | created_by_id | accounts_user | SET_NULL | created_fulfillments |
| fulfillment_comments | order_id | fulfillment_orders | CASCADE | comments |
| fulfillment_comments | author_id | accounts_user | SET_NULL | fulfillment_comments |

---

## 5. 인덱스 전체 현황

| 테이블 | 인덱스명 | 컬럼 | 타입 |
|--------|----------|------|------|
| accounts_user | (자동) email | email | UNIQUE |
| accounts_password_reset_codes | idx_reset_code_lookup | user, is_used, expires_at | Composite |
| clients | idx_client_company_name | company_name | B-tree |
| clients | idx_client_business_number | business_number | UNIQUE |
| clients | idx_client_is_active | is_active | B-tree |
| brands | uq_brand_client_name | client, name | UNIQUE |
| price_contracts | idx_price_contract_composite | client, work_type, valid_from, valid_to | Composite |
| price_contracts | uq_price_contract_client_type_item_from | client, work_type, item_name, valid_from | UNIQUE |
| products | (자동) barcode | barcode | B-tree (db_index) |
| products | (자동) option_code | option_code | B-tree (db_index) |
| products | unique_together | barcode, name | UNIQUE |
| locations | (자동) barcode | barcode | UNIQUE |
| inventory_records | inventory_r_barcode_79c384_idx | barcode | B-tree |
| inventory_records | inventory_r_session_a974d9_idx | session, location | Composite |
| orders | (자동) tracking_number | tracking_number | UNIQUE |
| orders | orders_status_762191_idx | status | B-tree |
| order_products | order_produ_barcode_dc87a5_idx | barcode | B-tree |
| inspection_logs | inspection__trackin_a758ee_idx | tracking_number | B-tree |
| inspection_logs | inspection__created_c7755b_idx | created_at | B-tree |
| fulfillment_orders | idx_fulfill_client_platform | client, platform | Composite |
| fulfillment_orders | idx_fulfill_status | status | B-tree |
| fulfillment_orders | idx_fulfill_order_number | order_number | B-tree |
| fulfillment_platform_column_configs | idx_platform_col_active | platform, is_active | Composite |
| fulfillment_platform_column_configs | uq_platform_column_key | platform, key | UNIQUE |

---

## 6. 주요 특이사항

1. **InspectionLog는 FK 없음** — tracking_number/barcode를 문자열로 저장 (Order와 직접 연결 안 됨)
2. **InventoryRecord.barcode도 FK 없음** — Product 테이블과 문자열 기반 조회
3. **FulfillmentOrder의 날짜 필드** — order_date, receiving_date가 CharField(50) (DateField에서 변환됨, 자유 형식 텍스트)
4. **Product.barcode**는 0002에서 UNIQUE 제거 → unique_together(barcode, name)으로 변경 (동일 바코드 다른 상품명 허용)
5. **Location.barcode** — 0011에서 기존 데이터 대문자 변환 + 중복 병합 완료, model save() 시 자동 upper()
6. **InboundRecord 이미지** — 단일 ImageField에서 InboundImage 다중 모델로 마이그레이션 완료 (0007→0010)
