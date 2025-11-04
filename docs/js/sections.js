// Tag only FIRST-LEVEL section headers in the left sidebar
document.addEventListener("DOMContentLoaded", () => {
    // find the root lists of the primary sidebar
    const rootLists = document.querySelectorAll(
      ".md-sidebar__inner nav.md-nav--primary > ul.md-nav__list"
    );
  
    rootLists.forEach((list) => {
      // only look at direct children (first level)
      list.querySelectorAll(":scope > li.md-nav__item").forEach((li) => {
        const first = li.firstElementChild;
        if (!first) return;
  
        // In Material, a section header that opens a group uses a <label.md-nav__link>
        // Pages are <a.md-nav__link>. We only want the <label> ones at the top level.
        const isTopLevelSection = first.matches("label.md-nav__link");
        const hasChildren = !!li.querySelector(":scope > nav, :scope > ul");
  
        if (isTopLevelSection && hasChildren) {
          li.classList.add("ev-section"); // our custom marker
        }
      });
    });
  });
  