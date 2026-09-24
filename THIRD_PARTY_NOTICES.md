# Third-party components

Capabilities this AIOS uses that are **made by someone else**. None of them is copied into this
repository, and the Funnel Futurist license (`LICENSE`) does not cover them. Each one is
installed from its maker, under the maker's own terms.

## Document skills - by Anthropic

| | |
|---|---|
| What they do | Create and edit Word (`docx`), PDF (`pdf`), PowerPoint (`pptx`) and Excel (`xlsx`) files |
| Made by | Anthropic, PBC |
| Source | [github.com/anthropics/skills](https://github.com/anthropics/skills) - plugin `document-skills` in the `anthropic-agent-skills` marketplace |
| Terms | Anthropic's own. Anthropic describes these four as *source-available, not open source*. Read `LICENSE.txt` in each skill's folder at the source |
| How this AIOS gets them | `.claude/settings.json` registers Anthropic's marketplace and enables the plugin. After you trust the folder in Claude Code, install it once with `/plugin install document-skills@anthropic-agent-skills`. `/onboard_wizard` walks you through it |

Until 2.6.0 the Starter carried a copy of these four skills. From 2.6.1 it installs them from
Anthropic instead, so you get Anthropic's current version and its updates, and Anthropic's
terms stay with Anthropic's files. An upgrade from 2.6.0 removes the old copies.
