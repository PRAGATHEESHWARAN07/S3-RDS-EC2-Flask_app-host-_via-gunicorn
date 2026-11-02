document.addEventListener("DOMContentLoaded", () => {
  const modal = document.getElementById("authModal");
  if (!modal) return;
  const loginPanel = document.getElementById("loginPanel");
  const registerPanel = document.getElementById("registerPanel");

  function showPanel(which) {
    loginPanel.hidden = which !== "login";
    registerPanel.hidden = which !== "register";
  }
  function openModal(which = "login") {
    showPanel(which);
    modal.classList.add("visible");
    modal.setAttribute("aria-hidden", "false");
  }
  function closeModal() {
    modal.classList.remove("visible");
    modal.setAttribute("aria-hidden", "true");
  }

  document.querySelectorAll("[data-open-modal]").forEach(button => {
    button.addEventListener("click", () => openModal(button.dataset.openModal));
  });
  document.querySelectorAll("[data-show-register]").forEach(button => {
    button.addEventListener("click", () => showPanel("register"));
  });
  document.querySelectorAll("[data-show-login]").forEach(button => {
    button.addEventListener("click", () => showPanel("login"));
  });
  modal.querySelector(".modal-close").addEventListener("click", closeModal);
  modal.addEventListener("click", event => {
    if (event.target === modal) closeModal();
  });
  document.addEventListener("keydown", event => {
    if (event.key === "Escape") closeModal();
  });

  if (window.location.hash === "#register") openModal("register");
  else if (window.location.hash === "#login") openModal("login");
});
