# Figma Rip Samples (v2 — Full Structure)

---

## 1. Pigeons & Planes — Header

---
component: Header
source: https://pigeonsandplanes.com
selector: header
semantic: header / banner
confidence: 85
size: 1920px × 120px
---

### Structure
```jsx
<header className="grid text-black transition">
  <div className="order-2 lg:order-1 flex items-center w-full space-x-6 pt-0 lg:pt-0 pb-3 sm:pt-0 md:pb-4 lg:pb-3 sm:pb-0">
    <div className="col-span-1">
      <a href="/">
        <img className="w-[50px] h-[50px]" alt="Pigeons & Planes Logo" />
      </a>
    </div>
    <nav className="relative w-full">
      <button className="bg-pp-dark cursor-pointer w-full lg:w-auto text-pp-white px-6 py-3 uppercase flex items-center ...">
        <span className="mr-auto lg:mr-0 lg:pr-20">MENU</span>
        <div className="w-6 h-6 rounded-full bg-pp-gray flex items-center justify-center">1 children</div>
      </button>
    </nav>
  </div>
  <div className="w-full order-1 lg:order-2 flex items-center justify-center">
    <a className="w-full" href="/">
      <svg className="w-full" /> {/* icon */}
    </a>
  </div>
  <div className="order-3 hidden lg:flex flex-row items-center justify-end space-x-6">
    <div className="flex justify-end space-x-3">
      <button className="text-pp-gray hover:text-pp-pink transition-colors hover:cursor-pointer" aria-label="Search">
        <svg className="lucide lucide-search w-6 h-6" /> {/* icon */}
      </button>
      <a className="text-pp-gray hover:text-pp-pink transition-colors" href="https://www.instagram.com/pigsandplans/" aria-label="Instagram">
        <svg className="lucide lucide-instagram w-6 h-6" /> {/* icon */}
      </a>
      <a className="text-pp-gray hover:text-pp-pink transition-colors" href="https://x.com/PigsAndPlans" aria-label="Twitter">
        <svg className="lucide lucide-twitter w-6 h-6" /> {/* icon */}
      </a>
      <a className="text-pp-gray hover:text-pp-pink transition-colors" href="https://www.youtube.com/@PigeonsAndPlanes" aria-label="YouTube">
        <svg className="lucide lucide-youtube w-6 h-6" /> {/* icon */}
      </a>
      <a href="https://www.tiktok.com/@pigsandplans" aria-label="TikTok">
        <div className="relative w-6 h-6">1 children</div>
      </a>
    </div>
    <div>
      <a className="items-center justify-between flex bg-pp-blue p-6 h-[30px] text-pp-white text-base uppercase ..." href="/newsletter">NEWSLETTER</a>
    </div>
  </div>
</header>
```

### Interactive States
| State | Changes |
|-------|--------|
| _(no interactive states detected)_ | — |

### Design Tokens Used
- **Color:** `text-black` (rgb(0, 0, 0))

### Anatomy
- **Root:** `<header>` (grid, 3-column, gap: 24px, columns: 608px 608px 608px)

---

## 2. Stripe — Navigation Bar

---
component: Navigation Bar
source: https://stripe.com
selector: nav
semantic: nav / navigation
confidence: 100
size: 1262px × 64px
---

### Structure
```jsx
<nav className="flex text-black h-16 transition">
  <a className="hds-link navigation-menu-home-link" href="/" aria-label="Stripe homepage">
    <svg aria-label="Stripe logo" /> {/* icon */}
  </a>
  <div className="hds-navigation-menu__content navigation-menu-content">
    <ul className="hds-navigation-menu__list navigation-menu-list hds-navigation-menu__list--horizontal">
      <li className="hds-navigation-menu__item navigation-item">
        <button className="hds-button hds-navigation-menu__trigger hds-button--transparent">Products</button>
      </li>
      <li className="hds-navigation-menu__item navigation-item">
        <button className="hds-button hds-navigation-menu__trigger hds-button--transparent">Solutions</button>
      </li>
      <li className="hds-navigation-menu__item navigation-item">
        <button className="hds-button hds-navigation-menu__trigger hds-button--transparent">Developers</button>
      </li>
      <li className="hds-navigation-menu__item navigation-item">
        <button className="hds-button hds-navigation-menu__trigger hds-button--transparent">Resources</button>
      </li>
      <li className="hds-navigation-menu__item navigation-item">
        <a className="hds-button hds-navigation-menu__trigger hds-button--transparent" href="/pricing">Pricing</a>
      </li>
      <li className="hds-navigation-menu__item navigation-item navigation-item__sign-in--mobile">
        <a className="hds-button hds-navigation-menu__trigger hds-button--transparent" href="https://dashboard.stripe.com/login">Sign in</a>
      </li>
    </ul>
  </div>
  <div className="navigation-menu-overflow">
    <section className="navigation-menu-footer">
      <div className="hds-button-group">
        <a className="hds-button hds-button--primary" href="https://dashboard.stripe.com/register">Start now</a>
        <a className="hds-button hds-button--secondary-on-quiet" href="/contact/sales">Contact sales</a>
      </div>
    </section>
    <section className="navigation-menu-header">
      <button className="hds-button navigation-back-button hds-button--transparent">
        <svg className="navigation__chevron-left-icon" /> {/* icon */}
      </button>
    </section>
  </div>
  <a className="hds-link navigation-item__contact-sales-mobile" href="/contact/sales">Contact sales</a>
  <button className="hds-ui-button hds-navigation-menu__trigger navigation-hamburger-button hds-ui-button--quiet" aria-label="Toggle navigation menu">
    <svg /> {/* icon */}
  </button>
  <ul className="navigation-buttons">
    <li className="hds-navigation-menu__item navigation-item">
      <a className="hds-button navigation-cta-button navigation-item__sign-in hds-button--secondary-on-quiet" href="https://dashboard.stripe.com/login" aria-label="Sign in">
        <svg className="navigation-item__sign-in__mask" /> {/* icon */}
        <span className="navigation-button-measure">Sign in</span>
      </a>
    </li>
    <li className="hds-navigation-menu__item navigation-item">
      <a className="hds-button navigation-cta-button navigation-item__contact-sales hds-button--primary" href="/contact/sales">
        <svg className="hds-icon hds-icon-hover-arrow" /> {/* icon */}
      </a>
    </li>
  </ul>
</nav>
```

### Interactive States
| State | Changes |
|-------|--------|
| _(no interactive states detected)_ | — |

### Design Tokens Used
- **Color:** `text-black` (rgb(0, 0, 0))

### Anatomy
- **Root:** `<nav>` (flex, row, align: center, gap: 28px)
