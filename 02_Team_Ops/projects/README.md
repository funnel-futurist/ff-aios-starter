# Projects

One folder per project, and each starts with its written plan: `PROJECT.md`. Copy `_template/` to start one.

`PROJECT.md` holds the meaning (the outcome, scope, decisions, acceptance, evidence). Your task tool (ClickUp or similar) holds the live tasks and links back here. When something changes in a meeting, update `PROJECT.md` first, then the tasks.

A website or app isn't a project folder: it lives in `03_RevOps/site/`, or in its own repository once it outgrows that.

**Upgraded from Starter 2.x?** Your old `11_Projects/` folders moved here unchanged. If one of them is a deployed site, change its Vercel **Root Directory** to the new path, or move it to `03_RevOps/site/` and point Vercel there. The upgrade lists any it found.
