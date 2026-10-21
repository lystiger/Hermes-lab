%% status: intended design (not built)

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
