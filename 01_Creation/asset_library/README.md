# Asset library

The one shared library. Every asset (a photo, a logo, a video, a screenshot, a testimonial) has one record, and every other folder points at it rather than copying it.

Each record is a short Markdown file next to the asset, named like it: `<asset>.md`.

| Field | What to write |
|---|---|
| Source | Where it came from, and who made it |
| Rights | Who owns it, and any limit on use |
| Approved uses | Where it may appear (site, ads, decks), and who approved that, with the date |
| Derivatives | Cropped or edited versions, and where they are |

An asset with no approved use isn't used publicly.
