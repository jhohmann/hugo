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
        if (!form.classList.contains("chat-form")) button.textContent = form.dataset.loadingText;
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

  // Nur der Verlauf scrollt; das Eingabefeld bleibt außerhalb davon.
  var messages = document.getElementById("messages");
  if (messages) {
    var followChat = true;

    function scrollChatToEnd() {
      if (followChat) messages.scrollTop = messages.scrollHeight;
    }

    messages.addEventListener("scroll", function () {
      followChat = messages.scrollHeight - messages.scrollTop - messages.clientHeight < 48;
    }, { passive: true });

    // Mobile Tastaturen verkleinern nicht in jedem Browser das CSS-Viewport.
    var viewport = window.visualViewport;
    var viewportFrame;
    function fitChatToViewport() {
      cancelAnimationFrame(viewportFrame);
      viewportFrame = requestAnimationFrame(function () {
        if (viewport && viewport.scale !== 1) return; // Pinch-Zoom nicht überschreiben.
        document.body.classList.toggle("chat-keyboard", window.innerWidth <= 760 &&
          (viewport ? viewport.height : window.innerHeight) < 500 &&
          document.activeElement && document.activeElement.id === "chat-message");
        document.body.style.setProperty("--chat-height", (viewport ? viewport.height : window.innerHeight) + "px");
        document.body.style.setProperty("--chat-top", (viewport ? viewport.offsetTop : 0) + "px");
        scrollChatToEnd();
      });
    }
    if (viewport) {
      viewport.addEventListener("resize", fitChatToViewport);
      viewport.addEventListener("scroll", fitChatToViewport);
    }
    window.addEventListener("resize", fitChatToViewport);
    messages.parentElement.addEventListener("focusin", fitChatToViewport);
    messages.parentElement.addEventListener("focusout", fitChatToViewport);
    if ("ResizeObserver" in window) {
      new ResizeObserver(scrollChatToEnd).observe(messages);
    }
    window.addEventListener("load", scrollChatToEnd);
    fitChatToViewport();
    scrollChatToEnd();
  }

  // Enter sendet (Umschalt+Enter = Zeilenumbruch).
  var chatInput = document.getElementById("chat-message");
  if (chatInput) {
    var threadPicker = document.getElementById("chat-thread");
    if (threadPicker) threadPicker.addEventListener("change", function () {
      if (!threadPicker.value) return;
      var reference = "V-" + threadPicker.value;
      var present = new RegExp("(^|[^\\w/-])" + reference + "(?![\\w-])", "i");
      if (!present.test(chatInput.value)) {
        var start = chatInput.selectionStart;
        var prefix = start && !/\s/.test(chatInput.value[start - 1]) ? " " : "";
        chatInput.setRangeText(prefix + reference + " ", start, chatInput.selectionEnd, "end");
      }
      threadPicker.value = "";
      chatInput.focus();
      chatInput.dispatchEvent(new Event("input", { bubbles: true }));
    });
    chatInput.addEventListener("keydown", function (event) {
      if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
        event.preventDefault();
        if (!chatInput.form.querySelector("button[type=submit]").disabled) chatInput.form.requestSubmit();
      }
    });
  }
});
