# 11_Projects

Where your deployable sites, apps, and internal tools live. One folder per project.

This is the home for anything Claude Code builds that goes ONLINE: a landing page, your main website, a small internal tool, a calculator. Each project gets its own folder here (e.g. `main-website/`, `lead-magnet/`).

## Deploying with Vercel
Point Vercel's **Root Directory** at the project subfolder, not the repo root. For your main site, set Root Directory = `11_Projects/main-website`. Vercel builds and deploys just that folder, push a change and the site updates automatically, and the rest of your brain stays private and untouched.

## Keep it here vs. its own repo
Keep a project here when it's lightweight: a landing page, a simple site, an internal tool you and your operator manage. Move it to its **own separate repo** only when it's a serious production app, a client-facing product, needs outside developer access, or needs its own permissions and secrets kept separate from your brain. Most things start here.

(`11_Projects/` and `10_Departments/` are optional. Create them when you actually have a project or a second department, not before.)
