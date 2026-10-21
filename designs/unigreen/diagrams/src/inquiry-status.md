%% status: intended design (not built)

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
