(() => {
  const menuButtons = document.querySelectorAll("[data-menu-button]");
  const menuRef = document.querySelector("[data-menu]");
  const themeBox = document.querySelector(".theme-switch__box");
  const desktopSlot = document.querySelector("[data-theme-desktop]");
  const mobileSlot = document.querySelector("[data-theme-mobile]");

  if (!menuRef || !menuButtons.length || !themeBox) return;

  const MODE = {
    MOBILE: "mobile",
    TABLET: "tablet",
    DESKTOP: "desktop",
  };

  const getMode = () => {
    const w = window.innerWidth;
    if (w <= 768) return MODE.MOBILE;
    if (w >= 1025) return MODE.DESKTOP;
    return MODE.TABLET;
  };

  let currentMode = null;

  const placeThemeSwitcher = () => {
    const mode = getMode();
    if (mode === currentMode) return;

    currentMode = mode;

    if (mode === MODE.MOBILE) {
      mobileSlot.appendChild(themeBox);
    } else {
      desktopSlot.appendChild(themeBox);
    }
  };

  const initMenuState = () => {
    if (getMode() !== MODE.DESKTOP) {
      menuRef.classList.remove("is-open");
      return;
    }

    const stored = localStorage.getItem("menu-is-open");
    menuRef.classList.toggle("is-open", stored !== "false");
  };

  placeThemeSwitcher();
  initMenuState();

  window.addEventListener("resize", placeThemeSwitcher);

  menuButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      const isOpen = menuRef.classList.toggle("is-open");

      if (currentMode === MODE.DESKTOP) {
        localStorage.setItem("menu-is-open", isOpen);
      }
    });
  });

  menuRef.querySelectorAll(".nav-link").forEach(link => {
    link.addEventListener("click", () => {
      if (currentMode !== MODE.DESKTOP) {
        menuRef.classList.remove("is-open");
      }
    });
  });

  document.documentElement.classList.add("menu-ready");
})();
