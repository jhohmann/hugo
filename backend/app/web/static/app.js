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

  // Erst das mobile Layout herstellen, danach die Scrollposition bestimmen.
  var panel = document.querySelector(".conversation-panel");
  if (panel && window.matchMedia("(max-width: 760px)").matches) {
    panel.removeAttribute("open");
  }

  // Das Eingabefeld gehört zum Scrollziel, damit es die Antwort nicht verdeckt.
  var chatMain = document.querySelector(".chat-main");
  if (chatMain) {
    var followChat = true;
    var previousScrollY = window.scrollY;

    function scrollChatToEnd() {
      if (!followChat) return;
      chatMain.scrollIntoView({ block: "end", behavior: "instant" });
      previousScrollY = window.scrollY;
    }

    window.addEventListener("scroll", function () {
      if (window.scrollY < previousScrollY) {
        followChat = false;
      } else if (chatMain.getBoundingClientRect().bottom <= window.innerHeight + 48) {
        followChat = true;
      }
      previousScrollY = window.scrollY;
    }, { passive: true });

    // Auch nachgeladenes Layout und wachsende Nachrichten berücksichtigen.
    if ("ResizeObserver" in window) {
      var chatResizeObserver = new ResizeObserver(scrollChatToEnd);
      chatResizeObserver.observe(chatMain);
      var header = document.querySelector(".site-header");
      if (header) chatResizeObserver.observe(header);
      if (panel) chatResizeObserver.observe(panel);
    }
    window.addEventListener("load", scrollChatToEnd);
    window.addEventListener("resize", scrollChatToEnd);
    var chatForm = chatMain.querySelector(".chat-form");
    if (chatForm) {
      chatForm.addEventListener("submit", function () {
        followChat = true;
        scrollChatToEnd();
      });
    }
    scrollChatToEnd();
  }

  // Enter sendet (Umschalt+Enter = Zeilenumbruch).
  var chatInput = document.getElementById("chat-message");
  if (chatInput) {
    chatInput.addEventListener("keydown", function (event) {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        chatInput.form.requestSubmit();
      }
    });
  }
});
