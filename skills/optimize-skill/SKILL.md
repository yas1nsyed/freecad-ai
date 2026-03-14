---
name: optimize-skill
description: Automatically optimize a skill's SKILL.md by running test cases, scoring results, and iteratively improving instructions
---

# Skill Optimizer

Optimizes a FreeCAD AI skill by iteratively running it against test cases,
evaluating the results, and using the LLM to improve the SKILL.md instructions.

Inspired by [autoresearch](https://github.com/karpathy/autoresearch).

## Usage

Type `/optimize-skill` to open the configuration dialog, or
`/optimize-skill skill-name` to pre-select a skill.

## How It Works

1. Select a skill and define test cases
2. The optimizer runs each test case, collects metrics (errors, completions, measurements)
3. The LLM analyzes failures and modifies the SKILL.md
4. Repeat until the score converges or iterations are exhausted
5. The best version is saved; the original is always backed up
