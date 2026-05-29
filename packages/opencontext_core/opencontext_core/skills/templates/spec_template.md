# Spec: {{ change_name }}

## Why

{{ why }}

## Capabilities

{% for cap in capabilities %}
- {{ cap }}
{% endfor %}

## Constraints

{% for constraint in constraints %}
- {{ constraint }}
{% endfor %}

## Non-Goals

{% for non_goal in non_goals %}
- {{ non_goal }}
{% endfor %}

## Success Signals

{% for signal in success_signals %}
- {{ signal }}
{% endfor %}

## Requirements

<!-- Add detailed requirements here, organized by domain -->

### Requirement: <!-- title -->

**Description**: <!-- what the system must do -->
**Scenarios**:
- <!-- scenario 1 -->
- <!-- scenario 2 -->
