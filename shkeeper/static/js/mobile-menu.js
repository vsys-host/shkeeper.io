(() => {
  const menuButtons = document.querySelectorAll("[data-menu-button]");
  const menuRef = document.querySelector("[data-menu]");

  if (!menuRef || !menuButtons.length) return;

  const DESKTOP_BREAKPOINT = 1025;

  const isDesktop = () => window.innerWidth >= DESKTOP_BREAKPOINT;

  let desktopMode = null;

  const updateMode = () => {
    desktopMode = isDesktop();
  };

  const initMenuState = () => {
    updateMode();

    if (!desktopMode) {
      menuRef.classList.remove("is-open");
      return;
    }

    const stored = localStorage.getItem("menu-is-open");
    menuRef.classList.toggle("is-open", stored !== "false");
  };

  initMenuState();
  window.addEventListener("resize", updateMode);

  menuButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      const isOpen = menuRef.classList.toggle("is-open");

      if (desktopMode) {
        localStorage.setItem("menu-is-open", isOpen);
      }
    });
  });

  menuRef.querySelectorAll(".nav-link").forEach(link => {
    link.addEventListener("click", () => {
      if (!desktopMode) {
        menuRef.classList.remove("is-open");
      }
    });
  });
})();