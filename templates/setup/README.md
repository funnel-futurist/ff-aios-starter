# SETUP.md templates, one per repository kind (estate workstream E3)

Every repository FF hands out carries a `SETUP.md` with the same seven parts, in the same order: name and registry row, access to grant (all up front), secrets, reviewer, hosting link, first-run checks, and what protects it. Each step a person does links a card in the Starter's `docs/human_steps/`. Link the published card; don't copy it.

| Kind | Template | Where it ends up |
|---|---|---|
| Instance (one company) | the Starter's own `SETUP.md` (ships with every install) | `<company>-os/SETUP.md`, `ff-00-instance/SETUP.md` |
| Intelligence (FF methods, `ff-NN-<domain>`) | `SETUP.intelligence.md` | P01's Intelligence skeleton in ai-os |
| Product or site (`ff-NN-<domain>-<surface>`) | `SETUP.product.md` | P01's product skeleton in ai-os |
| AIOS (`ai-os`) | `SETUP.aios.md` | ai-os root |

Replace every `<placeholder>`. Delete a row only when it truly doesn't apply, and say why in the row instead of leaving it blank.

Cards live at `https://github.com/funnel-futurist/ff-aios-starter/blob/main/docs/human_steps/`. This path changes when the repository is renamed to `ff-22-starter` in W6. GitHub redirects the old address.
