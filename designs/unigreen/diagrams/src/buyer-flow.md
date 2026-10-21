%% status: intended design (not built)

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
