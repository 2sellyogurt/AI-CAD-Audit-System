# Checkpoints

## Overview

The checkpoint system provides **deterministic, rule-based compliance checking** against Chinese national building codes (GB standards). Checkpoints are defined as YAML files and executed by the checkpoint engine.

## Checkpoint Coverage

| Discipline | Checkpoints | Key Standards |
|-----------|-------------|---------------|
| Building | 20+ | GB50016-2014 |
| Structure | 15+ | GB50011-2010, GB50010-2010 |
| Fire Protection | 15+ | GB50016, GB50974, GB51251 |
| HVAC | 15+ | GB50736, GB51251 |
| Plumbing | 12+ | GB50015, GB50242 |
| Electrical | 12+ | GB50016, GB50034, GB50054 |
| Curtain Wall | 8+ | JGJ102 |
| Decoration | 8+ | GB50222 |
| Landscape | 6+ | CJJ/T 82 |
| Foundation Pit | 6+ | JGJ120 |
| Symbols & Legend | 5+ | GB/T 50001 |

## Check Types

| Type | Description | Example |
|------|-------------|---------|
| `dimension_min` | Minimum dimension check | Door width >= 900mm |
| `dimension_max` | Maximum dimension check | Fire compartment <= 2500m² |
| `element_required` | Required element presence | Sprinkler in fire zone |
| `element_forbidden` | Prohibited element check | Combustible material in fire wall |
| `ratio_check` | Ratio/comparison check | Reinforcement ratio |
| `compatibility` | Compatibility check | Material fire rating vs. requirement |

## Review Routes

Each checkpoint can use one of three review routes:

| Route | Description |
|-------|-------------|
| `rule` | Deterministic rule-based check only |
| `llm` | LLM vision model review only |
| `dual` | Both rule-based and LLM review (cross-validated) |

## Example: Evacuation Door Width

```yaml
- id: JZ-001
  name: Evacuation Door Net Width Check
  description: Check if residential door and exit net width >= 0.90m
  discipline: building
  check_type: dimension_min
  route: dual
  severity: A
  priority: 100
  standard_code: GB50016-2014(2018)
  standard_clause: "5.5.30"
  clause_text: "Net width of residential doors and exits shall not be less than 0.90m"
  target_object: ["evacuation door", "residential door", "exit"]
  target_property: "net width"
  operator: ">="
  limit_value: 900
  unit: mm
  suggestion_template: "Increase evacuation door width to >= 900mm"
  applicable_building_types: ["all"]
```

## Example: Fire Compartment Area

```yaml
- id: XF-001
  name: Fire Compartment Area Check
  description: Check fire compartment area limits per GB50016
  discipline: fire
  check_type: dimension_max
  route: dual
  severity: A
  priority: 95
  standard_code: GB50016-2014(2018)
  standard_clause: "5.3.4"
  target_object: ["fire compartment"]
  target_property: "area"
  operator: "<="
  limit_value: 2500
  unit: m²
  suggestion_template: "Reduce fire compartment area or add sprinkler system"
  applicable_building_types: ["civil"]
```

## Adding Custom Checkpoints

1. Create or edit a YAML file in `v7/checkpoints/definitions/`
2. Follow the schema defined in `v7/checkpoints/checkpoint_schema.py`
3. Run validation: `python v7/checkpoints/engine.py --validate`
4. Restart the review pipeline

## Contributing Checkpoints

See [CONTRIBUTING.md](https://github.com/2sellyogurt/AI-CAD-Audit-System/blob/main/CONTRIBUTING.md) for guidelines on contributing new checkpoints. We especially welcome:
- Additional GB standard clauses
- International building codes (IBC, Eurocode)
- Specialized discipline checks
