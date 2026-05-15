# qa-pilot.dev Landing Page

Static one-page marketing site for qa-pilot.dev. Vanilla HTML + Tailwind CSS (CDN). No build step required.

## Local preview

```bash
# Python
python -m http.server 3000 --directory landing/

# Node
npx serve landing/
```

Then open http://localhost:3000.

## Deploy to Vercel (recommended)

1. Push this repo to GitHub (already done).
2. Go to [vercel.com](https://vercel.com) and import the `W3JDev/qa-pilot` repo.
3. In the Vercel project settings:
   - **Framework Preset**: Other
   - **Root Directory**: `landing`
   - **Output Directory**: `.` (leave blank / dot)
   - **Build Command**: _(leave empty — no build step)_
4. Add a custom domain: `qa-pilot.dev` in Vercel Domains settings.
5. Point your DNS `A` record to `76.76.21.21` (Vercel) and set an `AAAA` to `2606:4700:3033::ac43:9c13` or use Vercel's nameservers.
6. Click **Deploy**. Done.

## Deploy to Cloudflare Pages (alternative)

1. Go to [pages.cloudflare.com](https://pages.cloudflare.com) and connect your GitHub account.
2. Select `W3JDev/qa-pilot`.
3. Set **Root path** to `landing/` and leave build command empty.
4. Deploy.
5. Add `qa-pilot.dev` as a custom domain in the Pages project settings.

## Deploy to GitHub Pages

1. In the repo's **Settings > Pages**, set source to **Deploy from a branch**.
2. Pick branch `feat/landing-page-v0` (or `Lets-Coin` after merge) and folder `/landing`.
3. GitHub will serve the page at `https://w3jdev.github.io/qa-pilot/`.
4. For the real domain, add a `landing/CNAME` file containing `qa-pilot.dev`.

## Stack

- **HTML**: hand-written, semantic, accessible
- **CSS**: Tailwind CSS via CDN (`cdn.tailwindcss.com`) with custom config block
- **Fonts**: Inter via Google Fonts
- **No JavaScript framework** — a single `<script>` block for Tailwind config only
- **Zero dependencies** — deployable as a flat static file anywhere

## Brand tokens

| Token | Value |
|---|---|
| Background | `#0a0a0c` (obsidian) |
| Surface | `#111114`, `#18181c`, `#1e1e24` |
| Accent (gold) | `#c8a45c` |
| Gold light | `#dfc07e` |
| Gold muted | `#8a6d35` |
| Text primary | `#f0f0f0` |
| Text secondary | `#a0a0a8` |
| Border | `#2a2a32` |
| Font | Inter (300, 400, 500, 600, 700) |

## What to do next

- [ ] Register `qa-pilot.dev` domain
- [ ] Deploy to Vercel and set custom domain
- [ ] Wire waitlist form to Resend / ConvertKit / Loops
- [ ] Add `og:image` meta tag (1200x630 social card)
- [ ] Add `favicon.ico` and `apple-touch-icon.png`
- [ ] Set up Plausible or Fathom analytics (privacy-first)
- [ ] Add `/sitemap.xml` for SEO once domain is live
