// Hugo Weboberfläche – bewusst minimales JavaScript.
// Alles Wichtige funktioniert auch ohne JS; hier nur Komfort.

document.addEventListener("DOMContentLoaded", function () {
  // Ladezustand: Button sperren und Hinweis zeigen, solange
  // der Server (LLM-Aufruf) antwortet.
  document.querySelectorAll("form[data-loading-text]").forEach(function (form) {
    form.addEventListener("submit", function () {
      var button = form.querySelector("button[type=submit]");
      if (button) {
        button.disabled = true;
        button.textContent = form.dataset.loadingText;
      }
      var indicator = document.querySelector(".loading-indicator");
      if (indicator) indicator.hidden = false;
    });
  });

  // Bestätigungsdialog für destruktive Aktionen (z. B. Verwerfen).
  document.querySelectorAll("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      if (!window.confirm(form.dataset.confirm)) {
        event.preventDefault();
      }
    });
  });

  // Chat: Verlauf ans Ende scrollen, Enter sendet (Umschalt+Enter = Zeilenumbruch).
  var messages = document.getElementById("messages");
  if (messages) {
    messages.scrollIntoView({ block: "end" });
  }
  var chatInput = document.getElementById("chat-message");
  if (chatInput) {
    chatInput.addEventListener("keydown", function (event) {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        chatInput.form.requestSubmit();
      }
    });
  }

  // Auf kleinen Bildschirmen die Unterhaltungsliste einklappen.
  var panel = document.querySelector(".conversation-panel");
  if (panel && window.matchMedia("(max-width: 760px)").matches) {
    panel.removeAttribute("open");
  }
});
