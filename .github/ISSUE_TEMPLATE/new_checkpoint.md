---
name: New Checkpoint
about: Propose a new checkpoint rule for a building code clause
title: "[CHECKPOINT] "
labels: checkpoint
assignees: ''
---

## Standard Reference

- Standard code: [e.g., GB50016-2014(2018)]
- Clause number: [e.g., 5.5.30]
- Clause text: [paste the exact clause text]

## Checkpoint Details

- **Discipline**: [building / structure / HVAC / plumbing / electrical / fire / curtain_wall / decoration / landscape / foundation_pit]
- **Check type**: [dimension_min / dimension_max / required_element / fire_rating / area_limit / distance_min / other]
- **Route**: [rule (deterministic) / llm (vision model) / dual (both)]
- **Severity**: [A (mandatory) / B (important) / C (advisory)]

## Target Objects

What objects in the drawing should this checkpoint target? [e.g., "evacuation doors", "fire compartments"]

## Suggested YAML

```yaml
- id: [DISCIPLINE-NNN]
  name: [Checkpoint name]
  description: [What to check]
  discipline: [discipline]
  check_type: [check_type]
  route: [route]
  severity: [A/B/C]
  priority: [1-100]
  standard_code: [standard]
  standard_clause: "[clause]"
  clause_text: "[clause text]"
  target_object: ["object1", "object2"]
  target_property: "[property to check]"
  operator: "[>= / <= / == / contains]"
  limit_value: [numeric value]
  unit: [mm / m2 / m / ratio / etc]
  suggestion_template: "[fix suggestion]"
  applicable_building_types: ["all" / specific types]
```
