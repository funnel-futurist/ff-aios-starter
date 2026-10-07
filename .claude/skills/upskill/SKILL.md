---
name: upskill
description: Refresh your AIOS's skills so you stay current without bloating. Researches what Claude Code and the wider ecosystem currently offer that's relevant to YOUR actual workflows, grills you on skill-bloat (you can have 500 skills and use 10), and proposes what to ADD, UPDATE, or RETIRE, department by department. Run every few weeks, or whenever a department changes.
---

# Upskill: stay current, stay lean

You help the operator keep their AIOS sharp. Two failure modes you fight: **falling behind** (the tools change monthly and they're still on an old setup) and **bloat** (skills and files pile up, the brain gets slower and dumber, the garden grows weeds). Your job is to fix both in one pass. Be honest and decisive; recommend cuts, not just adds.

## Step 1: Map what they actually do
Ask, or read from `01_Foundations/` and `vision_mission_values.md`: **which departments are they running right now?** (e.g. acquisition, fulfillment/customer success, operations, finance, content.) For each, what are the recurring jobs? You're sizing the surface area their skills should cover.

## Step 2: Audit what they have (grill for bloat)
List the skills in `.claude/skills/`. For each, ask plainly: **"When did you last use this? Does it still earn its place?"** Flag:
- **Dead weight:** never/rarely used → propose RETIRE (archive it, don't fear deleting; git keeps history).
- **Stale:** points at an old tool, model, or workflow → propose UPDATE.
- **Load-bearing:** used often, working → keep.
The rule out loud: *a tight brain is a sharp brain. You might have 500 skills and use 10. Keep what earns its place; cut the rest.*

## Step 3: Research what's current (the look-it-up move)
For their real workflows, research what's available NOW (this changes fast, so check today, don't trust memory):
- **Go to the source:** Claude + Claude Code docs (https://docs.claude.com) for new built-in skills, commands, and capabilities.
- **The ecosystem:** Anthropic's skills repo (github.com/anthropics/skills), the Claude Code plugin marketplace, and reputable creators (YouTube, last 1-2 months). Use the unstuck protocol's NotebookLM/YouTube method to move fast.
- **Source quality matters:** prefer official docs and recent hands-on creators. Bad sources lead to bad skills. The more good sources, the better the recommendation.
Map findings to their departments: "for content you now do X, this capability would help."

## Step 4: Propose ADD / UPDATE / RETIRE, by department
Give a clear, short table per department: what to add (and why it's worth it), what to update, what to retire. **Gate every ADD with can-vs-should:** does it serve a job they actually do, or is it shiny? If shiny, cut it. Note anything that's use-at-your-own-risk, adopting the good ones early is how they get ahead, but they choose.

## Step 5: Act on the approved changes
With their go-ahead: add the new skills (only from sources they trust, never run an untrusted skill), update the stale ones, archive the dead ones to `09_Archive/`. Commit with a clear message so the change is reversible.

## The frame
Stay current AND stay lean. Elimination > addition. The point isn't more skills, it's the *right* skills for the work you actually do, kept sharp as the tools evolve.
