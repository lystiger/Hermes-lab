# Unigreen diagrams

Each diagram is Mermaid source. GitHub draws the blocks below. To render one elsewhere,
paste its block into the [Mermaid Live Editor](https://mermaid.live).
Regenerate this page with `python3 build_readme.py` after editing a source in `src/`.

## Sitemap

_status: intended design (not built)_

```mermaid
flowchart LR
  home["/en or /vi: Home"] --> products["/en/products · /vi/san-pham"]
  home --> manufacturing["Manufacturing"]
  home --> oem["OEM"]
  home --> contact["Contact"]
  products --> pdetail["Product detail /en/products/slug"]
  pdetail --> basket["Quotation list /en/basket · /vi/gio-hang"]
  basket --> inquiry["Request quotation /en/inquiry · /vi/inquiry"]
  inquiry --> thanks["Thank you"]
  home --> admin["/admin"]
  admin --> login["/admin/login"]
  login --> ainq["/admin/inquiries"]
  ainq --> ainqd["/admin/inquiries/id"]
  admin --> aprod["/admin/products"]
  admin --> acat["/admin/categories"]
```

## Buyer flow: product to quotation request

_status: intended design (not built)_

```mermaid
flowchart TD
  A([Visitor lands on Home]) --> B[Browse catalogue]
  B --> C{Found a product?}
  C -- no --> B
  C -- yes --> D[Product detail: pack, formats, specs]
  D --> E[Add to quotation list]
  E --> F{Keep browsing?}
  F -- yes --> B
  F -- no --> G[Open quotation list]
  G --> H[Fill contact name, email, company, phone, notes]
  H --> I{Valid?}
  I -- no --> H
  I -- yes --> J[Send quotation request]
  J --> K{Saved?}
  K -- yes --> L([Thank you: written pricing in two working days])
  K -- no --> M[Message: could not be sent, try again]
  M --> J
```

## Staff flow

_status: intended design (not built)_

```mermaid
flowchart TD
  A([Staff opens /admin]) --> B[Sign in]
  B --> C{Credentials ok?}
  C -- no --> D[Error, attempts limited] --> B
  C -- yes --> E[Inquiries list: search and filter]
  E --> F[Open an inquiry]
  F --> G[Customer submission, read only]
  F --> H[Change status]
  F --> I[Assign staff]
  F --> J[Add internal note]
  H --> K[Audit event recorded]
  I --> K
  J --> K
  K --> E
```

## Inquiry status lifecycle

_status: intended design (not built)_

```mermaid
stateDiagram-v2
  [*] --> new
  new --> qualified
  new --> spam
  new --> duplicate
  qualified --> quoted
  quoted --> won
  quoted --> lost
  spam --> [*]
  duplicate --> [*]
  won --> [*]
  lost --> [*]
```

## Submitting an inquiry

_status: intended design (not built)_

```mermaid
sequenceDiagram
  actor Buyer
  participant Web as Web app
  participant API as Backend API
  participant DB as Database
  Buyer->>Web: Send quotation request
  Web->>API: POST /api/v1/public/inquiries (Idempotency-Key)
  API->>DB: Build product snapshots from the catalogue
  alt product published
    DB-->>API: Snapshot ok
    API->>DB: Save inquiry and lines
    API-->>Web: 201 with reference
    Web-->>Buyer: Thank you
  else product missing or unpublished
    DB-->>API: Not found
    API-->>Web: 422 with field errors
    Web-->>Buyer: Message, keep the basket
  end
```

## Database (generated from the staging schema)

_status: generated from the Unigreen database schema (staging)_

```mermaid
erDiagram
  audit_events {
    uuid id PK
    uuid actor_staff_id
    varchar action
    varchar entity_type
    uuid entity_id
    varchar request_id
    json change_summary
    timestamp created_at
  }
  inquiries {
    uuid id PK
    varchar reference
    varchar status
    varchar contact_name
    varchar email
    varchar phone
    varchar company_name
    varchar tax_code
    varchar address
    varchar destination
    text notes
    text oem_requirements
    varchar locale
    varchar source
    uuid assigned_staff_id
    varchar idempotency_key
    timestamp created_at
    timestamp updated_at
    int version
  }
  inquiry_internal_notes {
    uuid id PK
    uuid inquiry_id
    uuid author_staff_id
    text content
    timestamp created_at
    timestamp updated_at
  }
  inquiry_lines {
    uuid id PK
    uuid inquiry_id
    uuid product_id
    varchar product_sku
    varchar product_name
    json product_snapshot
    numeric quantity
    varchar unit
    text requirements
    int sort_order
    timestamp created_at
    timestamp updated_at
    varchar pack_option
  }
  inquiry_sequences {
    int year
    int last_value
  }
  product_categories {
    uuid id PK
    varchar slug
    varchar status
    uuid parent_id
    int sort_order
    timestamp created_at
    timestamp updated_at
    int version
  }
  product_category_links {
    uuid product_id
    uuid category_id
    int sort_order
  }
  product_category_translations {
    uuid category_id
    varchar locale
    varchar name
    text description
    varchar meta_title
    varchar meta_description
  }
  product_media {
    uuid id PK
    uuid product_id
    varchar storage_key
    varchar checksum_sha256
    varchar original_filename
    varchar detected_mime_type
    bigint size_bytes
    int width
    int height
    varchar alt_vi
    varchar alt_en
    int sort_order
    boolean is_primary
    json variants
    varchar source_reference
    varchar approval_status
    timestamp created_at
  }
  product_specification_translations {
    uuid specification_id
    varchar locale
    varchar label
    varchar display_value_override
  }
  product_specifications {
    uuid id PK
    uuid product_id
    varchar key
    varchar value
    varchar unit
    int sort_order
    boolean is_highlighted
  }
  product_translations {
    uuid product_id
    varchar locale
    varchar name
    text summary
    text description
    varchar meta_title
    varchar meta_description
  }
  products {
    uuid id PK
    varchar sku
    varchar slug
    varchar barcode
    varchar status
    boolean oem_available
    boolean featured
    int sort_order
    timestamp published_at
    timestamp created_at
    timestamp updated_at
    int version
    json pack_options
    varchar canonical_product_id
  }
  staff_sessions {
    uuid id PK
    uuid staff_user_id
    varchar token_hash
    varchar csrf_token_hash
    timestamp expires_at
    timestamp revoked_at
    timestamp created_at
    timestamp last_seen_at
    varchar ip_hash
    varchar user_agent_summary
  }
  staff_users {
    uuid id PK
    varchar email
    text password_hash
    varchar role
    varchar status
    timestamp last_login_at
    timestamp created_at
    timestamp updated_at
    int version
  }
  staff_users ||--o{ audit_events : "references"
  staff_users ||--o{ inquiries : "references"
  inquiries ||--o{ inquiry_internal_notes : "references"
  staff_users ||--o{ inquiry_internal_notes : "references"
  inquiries ||--o{ inquiry_lines : "references"
  products ||--o{ inquiry_lines : "references"
  product_categories ||--o{ product_categories : "references"
  product_categories ||--o{ product_category_links : "references"
  products ||--o{ product_category_links : "references"
  product_categories ||--o{ product_category_translations : "references"
  products ||--o{ product_media : "references"
  product_specifications ||--o{ product_specification_translations : "references"
  products ||--o{ product_specifications : "references"
  products ||--o{ product_translations : "references"
  staff_users ||--o{ staff_sessions : "references"
```
