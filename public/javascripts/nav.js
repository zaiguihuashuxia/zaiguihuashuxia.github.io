// Material renders the fold arrow of the tab heading in the sidebar (笔记) without a tab stop,
// because it does not expect a section to fold; extra.css lets it fold, so make it reachable by
// keyboard too. Material clicks a focused label on Enter.
document$.subscribe(() => {
  const arrows = document.querySelectorAll(
    ".md-nav--lifted > .md-nav__list > .md-nav__item--section > .md-nav__link > label[for]"
  );
  for (const arrow of arrows) {
    arrow.tabIndex = 0;
  }
});
