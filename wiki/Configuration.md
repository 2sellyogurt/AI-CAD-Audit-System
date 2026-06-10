# Configuration

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ZHIPU_API_KEY` | No | ZhipuAI (GLM) API key |
| `DEEPSEEK_API_KEY` | No | DeepSeek API key |
| `OPENAI_API_KEY` | No | OpenAI or OpenAI-compatible API key |

At least one API key must be configured for LLM-powered review. Dry-run mode works without any API key.

## Project Configuration

Main configuration file: `v7/config/project_config.yaml`

```yaml
# LLM Provider settings
llm:
  provider: zhipuai       # zhipuai, deepseek, openai
  model: glm-4-flash      # Model name
  max_tokens: 4096
  temperature: 0.1

# Review settings
review:
  max_files: 50           # Max files per review
  timeout: 300            # Timeout per file (seconds)
  parallel_agents: 4      # Concurrent agent count
```

## Spatial Analysis Configuration

File: `v7/config.yaml`

Controls floor mapping, discipline classification, layer rules, and conflict detection parameters:

```yaml
# Floor name to number mapping
floor_map:
  B1F: -1
  1F: 1
  ...

# Discipline classification by filename prefix
discipline_rules:
  hvac: [h-, hvac, 暖通, ...]
  structure: [s-, 结施, 结构, ...]
  plumbing: [水施, 给排水, ...]
  electrical: [电施, 电气, ...]

# Conflict detection rules
conflict_rules:
  beam_duct:
    type: beam_duct_overlap
    severity: B
    std: "GB50010-2010 9.2.14"
    overlap_threshold: 300
```

## Checkpoint Management

Checkpoints are defined in YAML files under `v7/checkpoints/definitions/`:

| File | Discipline | Checkpoints |
|------|-----------|-------------|
| `building.yaml` | Building | Door width, stair width, corridor width |
| `structure.yaml` | Structure | Reinforcement ratio, beam-column joints |
| `fire.yaml` | Fire Protection | Compartment area, sprinkler coverage |
| `hvac.yaml` | HVAC | Duct sizing, smoke exhaust rate |
| `plumbing.yaml` | Plumbing | Pipe sizing, drainage slope |
| `electrical.yaml` | Electrical | Cable rating, emergency lighting |
| `curtain_wall.yaml` | Curtain Wall | Panel thickness, sealant width |
| `decoration.yaml` | Decoration | Material fire rating |
| `landscape.yaml` | Landscape | Planting distance, drainage |
| `foundation_pit.yaml` | Foundation Pit | Retaining structure, monitoring |
| `building_extra.yaml` | Building Extra | Additional building checks |
| `symbol_legend.yaml` | Symbols | Drawing symbol validation |

### Adding a New Checkpoint

Create a YAML entry with this format:

```yaml
- id: XX-001
  name: Checkpoint Name
  description: What this checkpoint validates
  discipline: building
  check_type: dimension_min
  route: dual
  severity: A
  priority: 100
  standard_code: GB50016-2014
  standard_clause: "X.X.X"
  target_object: ["door", "exit"]
  target_property: "net width"
  operator: ">="
  limit_value: 900
  unit: mm
  suggestion_template: "Increase width to >= 900mm"
  applicable_building_types: ["all"]
```

### Severity Levels

| Level | Meaning |
|-------|---------|
| A | Critical - must fix, affects safety |
| B | Important - should fix, affects compliance |
| C | Advisory - improvement suggestion |
