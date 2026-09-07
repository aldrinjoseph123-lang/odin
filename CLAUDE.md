# Theme — always use, no exceptions

Every addition or modification to this app's UI must use this theme. Do not introduce other colors, fonts, or radii without being explicitly told to change the theme itself.

Source: modeled on the Protect24x7 (localhost:5173) marketing site's visual language — dark/red tactical, sharp corners, uppercase tracked labels. App name is "Odin" (not rebranded as Protect24x7).

## Token architecture (defined in `static/style.css`)

Follows **shadcn/ui's token model** — adopted for its structure only. There is no
React, no Tailwind, and no build step: plain CSS consumed by Jinja templates.
Three layers, in order. Never skip one, and never let a component rule read a
layer-1 primitive directly.

1. **Primitives** — raw values, named for what they ARE: `--red-600`,
   `--neutral-950`, `--space-4`, `--text-sm`.
2. **Semantic** — roles, named for what they DO, using shadcn's
   foreground-pair convention (every surface has a matching text token):
   `--background/--foreground`, `--card/--card-foreground`,
   `--primary/--primary-foreground`, `--secondary/…`, `--muted/--muted-foreground`,
   `--destructive/…`, plus `--border-c`, `--input`, `--ring`, `--radius`.
3. **Component** — the classes, built only from layer 2.

Colors are stored as bare HSL triplets so any token can be tinted without a new
token: `hsl(var(--muted) / 0.6)`. Wrap in `hsl()` at point of use.

`--primary-text` is a darker step of the brand red, used wherever red is *text*
on a light surface: `#E11D2E` itself measures 4.39:1 there, just under WCAG AA's
4.5:1. Fills keep the exact brand hex (white on red is 4.75:1).

**Scales** (use these, don't invent values): spacing `--space-1..8` (4px base);
type `--text-2xs | xs | sm | base | lg | xl | 2xl | 3xl`; `--shadow-sm | shadow | shadow-md`.

The brand hexes stay exact, kept as aliases for inline template styles:

```css
--bg: #F6F6F4;          /* page background, off-white */
--dark: #0A0A0A;        /* nav bar, dark panels, table headers */
--dark-alt: #1C1C1C;    /* secondary dark surface */
--accent: #E11D2E;      /* primary red — buttons, links, active states */
--accent-hover: #B8101F;
--border: #D8D8D5;      /* light surface borders */
--border-dark: #4A4A4A; /* borders on dark surfaces */
--text: #0A0A0A;
--radius: 2px;          /* sharp corners everywhere — never rounded */
```

Dark mode is deliberately not defined (the app is a light surface with a dark
nav). If it's ever wanted, override layer 2 only inside a `.dark` block.

## Font

`"Chakra Petch"` (Google Fonts), loaded via `<link>` in every standalone `<head>` (base.html and the two report templates each load it — a new standalone page needs the same three `<link>` tags, not just the stylesheet).

## Conventions

- Buttons, nav links, `h3` section labels, table `th`, badges, filter pills: `text-transform: uppercase; letter-spacing: 0.04–0.06em; font-weight: 600`.
- Body copy, table data, free-text notes: normal case — don't uppercase user data or long text, only UI chrome/labels.
- Corners: `var(--radius)` (2px) on every button, input, panel, card, table — never the old rounded (6–8px) style.
- Nav bar and table headers = `--secondary` (dark) background, muted grey text, white for emphasis.
- **Buttons** use the shadcn variant model: `.btn` is the base; add `.btn-secondary`,
  `.btn-outline`, `.btn-ghost`, or `.btn-sm`. A bare `<button>` inside a form
  inherits the primary skin, so pre-variant markup keeps working.
- Reuse `.kv`, `.panel`, `.card`, `.stage-badge`, `.countdown`, `.icon-btn`,
  `.btn-link`, `.link-btn`, `.filters` from `static/style.css` instead of
  inventing ad-hoc styles.
- Form controls are `width: 100%` by default. A row of inline controls must opt
  out explicitly (see `.task-form` / `.search-form` / `.upload-form`) or it
  silently becomes a vertical stack.

## When adding a new page/template

1. Extend `base.html` where possible (gets nav, font, flash styling for free).
2. If it must be standalone (like the print reports), copy the two `<link rel="preconnect">` + Google Fonts `<link>` + `style.css` link from `report_single.html`.
3. Use the CSS custom properties above — don't hardcode hex colors inline.
