(() => {
  const menuBtnRef = document.querySelector("[data-menu-button]");
  const mobileMenuRef = document.querySelector("[data-menu]");


  menuBtnRef.addEventListener("click", () => {
    mobileMenuRef.classList.toggle("is-open");

    localStorage.setItem('menu-is-open', mobileMenuRef.classList.contains("is-open"));
  });

  // if (localStorage.getItem('menu-is-open') === 'false') {
  //   mobileMenuRef.classList.remove("is-open");
  // }

})();