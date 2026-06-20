# OpenSpec Agent Instructions

This file provides instructions for AI coding assistants working with the OpenSpec workflow in this project.

## Overview

OpenSpec is a Spec-Driven Development (SDD) framework that establishes a "living specification" as the single source of truth. All feature development follows a structured workflow to ensure alignment between requirements and implementation.

## Directory Structure

```
openspec/
├── AGENTS.md           ← This file (AI instructions)
├── project.md          ← Project context and conventions
├── specs/              ← Source of truth specifications
├── changes/            ← Active change proposals
│   └── {change-id}/
│       ├── proposal.md ← What and why
│       ├── tasks.md    ← Implementation checklist
│       └── specs/      ← Delta specifications
└── archive/            ← Completed changes history
```

## Workflow Commands

### 1. `/openspec-proposal <description>`

**Purpose:** Create a new change proposal.

**What to generate:**
1. Create `openspec/changes/{change-id}/` directory
2. Create `proposal.md` with problem, solution, scope, impact
3. Create `tasks.md` with implementation checklist
4. Create `specs/{component}_delta.md` with specification changes

**Change ID Format:** `kebab-case-description` (e.g., `add-user-search`)

### 2. `/openspec-apply <change-id>`

**Purpose:** Implement the proposed change.

**What to do:**
1. Read `openspec/changes/{change-id}/proposal.md`
2. Follow tasks in `openspec/changes/{change-id}/tasks.md`
3. Mark tasks as complete `[x]` as you progress
4. Ensure implementation matches delta specs
5. Run quality checks after each phase

**Implementation Rules:**
- Follow project conventions in `project.md`
- Maintain existing patterns from project's CLAUDE.md
- Write tests for new functionality
- Update documentation as needed

### 3. `/openspec-archive <change-id>`

**Purpose:** Complete a change and update source of truth.

**What to do:**
1. Verify all tasks in `tasks.md` are complete
2. Merge delta specs into `openspec/specs/`
3. Move change directory to `openspec/archive/{change-id}/`
4. Add completion timestamp to archived proposal

## Delta Spec Format

Delta specs describe changes relative to existing specifications:

```markdown
# Delta: {Component Name}

## ADDED

### {New Requirement/Feature}
Description of new functionality...

#### Scenario: {Scenario Name}
- GIVEN {precondition}
- WHEN {action}
- THEN {expected result}

## MODIFIED

### {Existing Requirement}
Updated description...

## REMOVED

### {Deprecated Requirement}
Reason for removal...
```

## Quality Standards

Before archiving, verify:
- [ ] All tasks marked complete
- [ ] Tests passing
- [ ] Code quality verified
- [ ] Documentation synced
- [ ] Delta specs accurately reflect changes

## When to Use OpenSpec

| Scenario | Recommendation |
|----------|----------------|
| New major feature | Use OpenSpec |
| Cross-team collaboration | Use OpenSpec |
| Complex multi-phase changes | Use OpenSpec |
| Bug fixes | Skip OpenSpec |
| Small enhancements | Optional |
| Rapid prototyping | Skip OpenSpec |
