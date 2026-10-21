%% status: intended design (not built)

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
