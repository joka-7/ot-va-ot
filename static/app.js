/*
 * אות ואות — frontend.
 *
 * Plain ES2020, no build step and no framework. The server does the matching
 * and returns highlight offsets, so this file is only concerned with asking,
 * rendering, and the small interactions around a result (copy, show more,
 * language switching).
 *
 * The UI supports Hebrew, English and French (see i18n.js, loaded before this
 * file). The Tanakh verse text and its citation are never translated -- they
 * stay in Hebrew in every locale, same as the tradition this app is for.
 */

(function () {
  "use strict";

  // Mobile browsers skip :active/tap-highlight rendering on pages with no
  // touch listeners (treated as passively scrollable) -- this one-time
  // no-op listener makes tap feedback on the footer icon links actually
  // render.
  document.addEventListener("touchstart", function () {}, { passive: true });

  var t = I18N.t;
  var plural = I18N.plural;

  var LOCALE_STORAGE_KEY = "pasuk-leshem:locale";

  var form = document.getElementById("search-form");
  var input = document.getElementById("names");
  var submit = document.getElementById("submit");
  var clearBtn = document.getElementById("clear");
  var results = document.getElementById("results");
  var searchHeadEl = document.getElementById("search-head");
  var toastEl = document.getElementById("toast");
  var wakingEl = document.getElementById("waking");
  var langSwitch = document.getElementById("lang-switch");
  var installSection = document.getElementById("install-section");
  var installBtn = document.getElementById("install-btn");
  var installHint = document.getElementById("install-hint");
  var settingsBtn = document.getElementById("settings-btn");
  var settingsDialog = document.getElementById("settings-dialog");
  var modeSwitch = document.getElementById("mode-switch");
  var anyOrderLabel = document.getElementById("any-order-label");
  var anyOrderBox = document.getElementById("any-order");
  var examplesName = document.getElementById("examples");
  var examplesText = document.getElementById("examples-text");
  var niqqudBox = document.getElementById("niqqud");
  var niqqudToggle = document.getElementById("niqqud-toggle");
  var niqqudPad = document.getElementById("niqqud-pad");

  // Verses held back behind a "show more" button, keyed by group id.
  var pending = Object.create(null);
  var groupSeq = 0;

  // Lets a new search cancel the request still in flight behind it.
  var inFlight = null;

  // The hash of the search whose results are on screen, so the Search tab can put
  // it back after a visit to the reader.
  var searchHash = "";

  // The current UI language, and enough state to redraw without a network
  // round-trip when it changes: the last successful search response.
  var locale = loadLocale();
  var lastSearchData = null;
  var searchShowingSaved = false; // the results on screen are a copy kept on the device
  var lastSearchQuery = ""; // the query that produced lastSearchData, which the box may no longer show
  var lastSearchMode = "name"; // and the mode and word order it was made in
  var lastSearchAnyOrder = false;

  // What the search box means right now: "name" (letters of a name, the app's
  // original purpose) or "text" (a word or phrase anywhere in the Tanakh).
  // "anyOrder" only applies to text: all the words, in any order, rather than
  // next to each other.
  var mode = "name";
  var anyOrder = false;

  function loadLocale() {
    try {
      var stored = localStorage.getItem(LOCALE_STORAGE_KEY);
      if (stored && I18N.isSupported(stored)) return stored;
    } catch (err) {
      /* private browsing / storage disabled -- fall through to the default */
    }
    return I18N.DEFAULT_LOCALE;
  }

  function saveLocale(value) {
    try {
      localStorage.setItem(LOCALE_STORAGE_KEY, value);
    } catch (err) {
      /* not persisted this session; the switcher still works */
    }
  }

  var DIR = { he: "rtl", en: "ltr", fr: "ltr" };

  // --- Small helpers ---------------------------------------------------------

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  /*
   * A run of Hebrew text (a book name, the verse itself) embedded inside a
   * page that may currently be laid out left-to-right. Isolating it keeps the
   * bidi algorithm from reordering it around neighbouring digits or
   * punctuation -- without this, "Chapter 5" next to a Hebrew book name can
   * render with the number on the wrong side.
   */
  function hebrewSpan(tag, className, text) {
    var node = el(tag, className, text);
    node.setAttribute("dir", "rtl");
    return node;
  }

  // Free hosts sleep the server when idle and take up to a minute to wake on
  // the next request. Rather than let that look like the app has frozen, show
  // a notice -- but only once a request has been pending a couple of seconds,
  // so it never appears on an ordinary warm response.
  //
  // Reference-counted rather than a single flag/timer: on page load with a
  // #q= hash, the health check and the search fire at the same time, and one
  // finishing quickly must not hide the banner out from under the other one
  // that is still genuinely waiting on a cold host.
  var WAKE_DELAY_MS = 2500;
  var wakeTimer = null;
  var wakingRefs = 0;

  function armWaking() {
    wakingRefs++;
    if (wakingRefs === 1) {
      wakeTimer = setTimeout(function () {
        wakingEl.hidden = false;
      }, WAKE_DELAY_MS);
    }
    var disarmed = false;
    return function disarmWaking() {
      if (disarmed) return; // guard against a stray double-call
      disarmed = true;
      wakingRefs = Math.max(0, wakingRefs - 1);
      if (wakingRefs === 0) {
        clearTimeout(wakeTimer);
        wakingEl.hidden = true;
      }
    };
  }

  function toast(message) {
    toastEl.textContent = message;
    toastEl.classList.add("show");
    clearTimeout(toast.timer);
    toast.timer = setTimeout(function () {
      toastEl.classList.remove("show");
    }, 1900);
  }

  // --- Talking to the API ------------------------------------------------------

  /*
   * fetch, but patient about a sleeping backend.
   *
   * On the free plan the API sleeps after 15 idle minutes and takes up to a
   * minute to come back. The page is served from a CDN and so paints long
   * before that, and the request that arrives meanwhile does not simply wait:
   * whatever sits in front of the API answers first, with a gateway error or a
   * dropped connection, well before the app itself is up. Retrying is what
   * turns that into the wait it looks like it should be -- the caller's promise
   * stays pending, so the "waking the server" notice stays up and the request
   * completes on its own once the API answers.
   *
   * Only transport failures and gateway statuses are retried. A 4xx is the API
   * itself talking (a bad query) and is returned as-is.
   */
  var WAKE_RETRY_BUDGET_MS = 90000;
  var WAKE_RETRY_STEPS_MS = [1000, 2000, 3000, 5000, 5000, 8000];
  var GATEWAY_STATUSES = [502, 503, 504];

  function apiFetch(path, options) {
    options = options || {};
    // With no connection at all there is no server to wake: fail now rather than retry.
    if (navigator.onLine === false && !/^(localhost|127\.0\.0\.1)$/.test(location.hostname)) {
      return Promise.reject(new Error("offline"));
    }
    var deadline = Date.now() + WAKE_RETRY_BUDGET_MS;

    function attempt(n) {
      return fetch(window.API_BASE + path, options).then(function (response) {
        if (GATEWAY_STATUSES.indexOf(response.status) === -1) return response;
        return retryOr(n, response, null);
      }, function (error) {
        // The caller aborted (a superseded search) -- not a failure to retry.
        if (error && error.name === "AbortError") throw error;
        return retryOr(n, null, error);
      });
    }

    function retryOr(n, response, error) {
      var waitMs = WAKE_RETRY_STEPS_MS[n] || WAKE_RETRY_STEPS_MS[WAKE_RETRY_STEPS_MS.length - 1];
      if (n + 1 > WAKE_RETRY_STEPS_MS.length || Date.now() + waitMs > deadline) {
        if (response) return response;
        throw error;
      }
      if (options.signal && options.signal.aborted) throw new Error("aborted");
      return new Promise(function (resolve) { setTimeout(resolve, waitMs); })
        .then(function () { return attempt(n + 1); });
    }

    return attempt(0);
  }

  // --- Localized formatting ---------------------------------------------------

  /* The badge/citation number: Hebrew gematria in the Hebrew locale (the
     traditional form, e.g. "פרק ה׳"), plain digits otherwise ("Chapter 5"). */
  function localizedNumber(verse, field) {
    return locale === "he" ? verse[field + "He"] : String(verse[field]);
  }

  function bookName(verse) {
    return verse.book[locale] || verse.book.he;
  }

  // --- Rendering -------------------------------------------------------------

  /*
   * Build a verse's text with its matched letters wrapped in <mark>.
   *
   * `highlights` are character offsets into the raw verse text, computed by the
   * server (which knows how to keep a letter together with its niqqud). They
   * arrive sorted and non-overlapping, so a single pass is enough. Text is
   * added via textContent, so nothing here can inject markup.
   */
  function renderVerse(text, highlights) {
    var p = hebrewSpan("p", "verse");
    var at = 0;

    (highlights || []).forEach(function (h) {
      if (h.start < at) return; // defensive: ignore any overlap
      if (h.start > at) p.appendChild(document.createTextNode(text.slice(at, h.start)));
      p.appendChild(el("mark", h.kind, text.slice(h.start, h.end)));
      at = h.end;
    });

    if (at < text.length) p.appendChild(document.createTextNode(text.slice(at)));
    return p;
  }

  function copyButton(verse) {
    var button = el("button", "copy", t(locale, "copy.button"));
    button.type = "button";

    button.addEventListener("click", function () {
      var payload = verse.text + "\n(" + verse.ref + ")";

      function done() {
        button.textContent = t(locale, "copy.done");
        button.classList.add("done");
        toast(t(locale, "copy.toastCopied"));
        setTimeout(function () {
          button.textContent = t(locale, "copy.button");
          button.classList.remove("done");
        }, 1900);
      }

      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(payload).then(done, legacyCopy);
      } else {
        legacyCopy();
      }

      // Older mobile Safari has no async clipboard outside a secure context.
      function legacyCopy() {
        var area = document.createElement("textarea");
        area.value = payload;
        area.setAttribute("readonly", "");
        area.style.position = "fixed";
        area.style.opacity = "0";
        document.body.appendChild(area);
        area.select();
        try {
          document.execCommand("copy");
          done();
        } catch (err) {
          toast(t(locale, "copy.toastFailed"));
        }
        document.body.removeChild(area);
      }
    });

    return button;
  }

  /*
   * Hands the verse off to whatever the OS offers to share text with
   * (Messages, WhatsApp, Mail, …) via the Web Share API. Browsers without it
   * (most desktop browsers) fall back to the same clipboard copy the Copy
   * button does, so the action is never a dead end -- just a slower one.
   */
  function shareButton(verse) {
    var button = el("button", "copy", t(locale, "share.button"));
    button.type = "button";

    button.addEventListener("click", function () {
      var payload = verse.text + "\n(" + verse.ref + ")";

      function legacyCopy() {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(payload).then(function () {
            toast(t(locale, "copy.toastCopied"));
          }, function () {
            toast(t(locale, "copy.toastFailed"));
          });
          return;
        }
        var area = document.createElement("textarea");
        area.value = payload;
        area.setAttribute("readonly", "");
        area.style.position = "fixed";
        area.style.opacity = "0";
        document.body.appendChild(area);
        area.select();
        try {
          document.execCommand("copy");
          toast(t(locale, "copy.toastCopied"));
        } catch (err) {
          toast(t(locale, "copy.toastFailed"));
        }
        document.body.removeChild(area);
      }

      if (navigator.share) {
        navigator.share({ text: payload }).catch(function (err) {
          if (err && err.name === "AbortError") return; // the visitor cancelled the share sheet
          legacyCopy();
        });
      } else {
        legacyCopy();
      }
    });

    return button;
  }

  /*
   * Rashi's commentary, hidden behind a native <details> disclosure -- same
   * pattern as `exampleDisclosure` below, closed by default so a card stays
   * short until the reader chooses to open it. Only rendered when the verse
   * has one: Rashi didn't comment on every verse in the Tanakh.
   *
   * `verse.rashi` is set via .innerHTML rather than .textContent because it
   * carries a few marks (the phrase Rashi is glossing, in <b>) as HTML. That
   * HTML is produced at dataset build time from Sefaria's text, not from user
   * input, and is limited there to a hand-verified tag whitelist
   * (<b>/<small>/<br> -- see scripts/build_dataset.py's clean_rashi_comment).
   */
  function rashiDisclosure(verse) {
    if (!verse.rashi) return null;

    var details = document.createElement("details");
    details.className = "rashi";
    details.dataset.order = "0";
    var summary = document.createElement("summary");
    summary.textContent = t(locale, "rashi.toggle");
    details.appendChild(summary);

    var body = hebrewSpan("div", "rashi-text", null);
    body.innerHTML = verse.rashi;
    details.appendChild(body);

    return details;
  }

  function verseCard(verse, note) {
    var card = el("article", "card");

    var head = el("div", "card-head");
    head.appendChild(hebrewSpan("span", "badge badge-book", bookName(verse)));
    head.appendChild(el("span", "badge", t(locale, "badge.chapter", { n: localizedNumber(verse, "chapter") })));
    head.appendChild(el("span", "badge", t(locale, "badge.verse", { n: localizedNumber(verse, "verse") })));
    if (note) head.appendChild(el("span", "badge badge-note", note));
    card.appendChild(head);

    card.appendChild(renderVerse(verse.text, verse.highlights));

    var foot = el("div", "card-foot");
    foot.appendChild(copyButton(verse));
    foot.appendChild(shareButton(verse));
    foot.appendChild(readerLink(verse));
    card.appendChild(foot);

    var rashi = rashiDisclosure(verse);
    if (rashi) card.appendChild(rashi);

    return card;
  }

  /*
   * One result group: a heading, an optional description, the verses, and a
   * "show more" button when the group was capped.
   */
  /*
   * A collapsed "show example" disclosure, added under a group's description
   * when one exists for it (see I18N.example -- empty until worked examples
   * are supplied). Uses the native <details> element: closed by default, no
   * JS needed to reveal it, and it stays keyboard- and screen-reader-friendly
   * for free.
   */
  function exampleDisclosure(text) {
    var details = document.createElement("details");
    details.className = "example";
    var summary = document.createElement("summary");
    summary.textContent = t(locale, "group.exampleToggle");
    details.appendChild(summary);
    details.appendChild(hebrewSpan("p", "example-text", text));
    return details;
  }

  function renderGroup(titleKey, descKey, descVars, group, exampleKey, note) {
    if (!group || !group.total) return null;

    var section = el("section", "group");
    section.dataset.total = group.total;
    var head = el("div", "group-head");
    head.appendChild(el("h3", "group-title", t(locale, titleKey)));

    var shown = group.verses.length;
    var label = shown < group.total
      ? t(locale, "count.showingOf", { shown: I18N.formatNumber(locale, shown), totalPhrase: plural(locale, "footer.verses", group.total) })
      : plural(locale, "footer.verses", group.total);
    head.appendChild(el("span", "group-count", label));
    section.appendChild(head);

    if (descKey) section.appendChild(el("p", "group-desc", t(locale, descKey, descVars)));

    var exampleText = exampleKey && I18N.example(locale, exampleKey);
    if (exampleText) section.appendChild(exampleDisclosure(exampleText));

    var visible = group.verses.slice(0, 10);
    var rest = group.verses.slice(10);
    visible.forEach(function (verse) {
      section.appendChild(verseCard(verse, note));
    });

    if (rest.length) {
      var id = "g" + groupSeq++;
      pending[id] = { verses: rest, note: note };
      var more = el("button", "more", t(locale, "more.button", { n: rest.length }));
      more.type = "button";
      more.dataset.group = id;
      more.addEventListener("click", function () {
        var held = pending[id];
        held.verses.forEach(function (verse) {
          section.insertBefore(verseCard(verse, held.note), more);
        });
        delete pending[id];
        more.remove();
      });
      section.appendChild(more);
    }

    return section;
  }

  function renderPair(pair) {
    var wrapper = el("div", "pair");

    var top = el("div", "pair-link");
    top.appendChild(hebrewSpan("span", "pair-name", pair.firstName));
    wrapper.appendChild(top);
    wrapper.appendChild(verseCard(pair.first));

    var link = el("div", "pair-link");
    link.appendChild(hebrewSpan("span", "pair-name", pair.secondName));
    wrapper.appendChild(link);
    wrapper.appendChild(verseCard(pair.second, pair.crossesChapter ? t(locale, "badge.crossesChapter") : null));

    return wrapper;
  }

  function renderPairGroup(titleKey, descKey, descVars, exampleKey, pairs) {
    if (!pairs || !pairs.length) return null;

    var section = el("section", "group");
    section.dataset.total = pairs.length;
    var head = el("div", "group-head");
    head.appendChild(el("h3", "group-title", t(locale, titleKey, descVars)));
    head.appendChild(el("span", "group-count", plural(locale, "pair.matches", pairs.length)));
    section.appendChild(head);

    if (descKey) section.appendChild(el("p", "group-desc", t(locale, descKey, descVars)));
    var exampleText = exampleKey && I18N.example(locale, exampleKey);
    if (exampleText) section.appendChild(exampleDisclosure(exampleText));

    pairs.forEach(function (pair) {
      section.appendChild(renderPair(pair));
    });
    return section;
  }

  /*
   * All pair-based results (consecutive / reversed / near-miss) for one duo
   * out of the search's names. With two names there is exactly one of these;
   * with three, one per possible pair, each independently labeled with which
   * two names it covers so they're never ambiguous next to one another.
   */
  function renderPairGroupSet(pairGroup) {
    var names = pairGroup.names;
    var vars = { name1: names[0], name2: names[1] };
    var sections = [
      renderPairGroup("pair.consecutive.title", "pair.consecutive.desc", vars, "pair.consecutive", pairGroup.consecutive),
      renderPairGroup("pair.reversed.title", "pair.reversed.desc", vars, "pair.reversed", pairGroup.reversed),
      renderPairGroup("pair.nearMiss.title", "pair.nearMiss.desc", vars, "pair.nearMiss", pairGroup.nearMiss),
    ].filter(Boolean);

    if (!sections.length) {
      return [notice(t(locale, "pair.empty.title", vars), t(locale, "pair.empty.desc", vars))];
    }
    return sections;
  }

  /*
   * Results of a text search: one header with the query, then the whole-word
   * tier and the inside-a-longer-word tier -- the same two tiers (and the same
   * group markup) the name search uses for "the name appears in the verse".
   */
  function renderPhrase(data) {
    results.innerHTML = "";
    pending = Object.create(null);
    results.appendChild(el("p", "tap-hint", t(locale, "results.tapWordHint")));

    var header = el("div", "name-head");
    header.appendChild(hebrewSpan("h2", null, data.query.text));
    if (data.query.words > 1) {
      header.appendChild(el("span", "name-letters", t(locale, data.query.ordered ? "phrase.ordered" : "phrase.anywhere")));
    }
    results.appendChild(header);

    var exactDesc = data.query.ordered ? "phrase.exact.desc.ordered" : "phrase.exact.desc.anywhere";
    var groups = [
      renderGroup("phrase.exact.title", exactDesc, null, data.exact, null),
      renderGroup("phrase.partial.title", "group.partialWord.desc", null, data.partial, null),
    ].filter(Boolean);

    if (!groups.length) {
      results.appendChild(
        notice(t(locale, "phrase.empty.title", { text: data.query.text }), t(locale, "phrase.empty.desc"))
      );
      return;
    }
    groups.forEach(function (group) {
      results.appendChild(group);
    });
    addSummary();
  }

  function render(data) {
    renderResults(data);
    if (searchShowingSaved) results.insertBefore(el("p", "attribution", t(locale, "reader.savedCopy")), results.firstChild);
  }

  function renderResults(data) {
    if (data.exact) {
      renderPhrase(data);
      return;
    }

    results.innerHTML = "";
    pending = Object.create(null);
    results.appendChild(el("p", "tap-hint", t(locale, "results.tapWordHint")));

    var any = false;

    if (data.query.mode === "multi") {
      data.pairs.forEach(function (pairGroup) {
        renderPairGroupSet(pairGroup).forEach(function (node) {
          results.appendChild(node);
          any = true;
        });
      });
    }

    data.names.forEach(function (entry) {
      var header = el("div", "name-head");
      header.appendChild(hebrewSpan("h2", null, entry.name));
      header.appendChild(el("span", "name-letters", entry.first + " … " + entry.last));
      results.appendChild(header);

      var letterVars = { first: entry.first, last: entry.last };
      var groups = [
        renderGroup("group.letterMatch.title", "group.letterMatch.desc", letterVars, entry.letterMatch, "group.letterMatch"),
        renderGroup("group.exactWord.title", "group.exactWord.desc", null, entry.exactWord, "group.exactWord"),
        renderGroup("group.partialWord.title", "group.partialWord.desc", null, entry.partialWord, "group.partialWord"),
      ];

      var found = false;
      groups.forEach(function (group) {
        if (group) {
          results.appendChild(group);
          found = true;
          any = true;
        }
      });

      if (!found) {
        results.appendChild(
          notice(
            t(locale, "group.empty.title", { name: entry.name }),
            t(locale, "group.empty.desc", letterVars)
          )
        );
      }
    });
    addSummary();
  }

  /*
   * A strip of jump links at the top of the results, one per result group with
   * its total, so the whole shape of the answer is visible without scrolling
   * and any group is one tap away. Only worth showing when there is more than
   * one group to choose between. In a multi-name search the group titles repeat
   * per name, so each chip is prefixed with the name it belongs to.
   */
  function addSummary() {
    var groups = Array.prototype.slice.call(results.querySelectorAll("section.group"));
    if (groups.length < 2) return;

    var nav = el("nav", "results-summary");
    nav.setAttribute("aria-label", t(locale, "results.summaryAria"));
    groups.forEach(function (group) {
      var owner = group.previousElementSibling;
      while (owner && !owner.classList.contains("name-head")) {
        owner = owner.previousElementSibling;
      }
      var prefix = owner && owner.classList.contains("name-head") && results.querySelectorAll(".name-head").length > 1
        ? owner.querySelector("h2").textContent + " · "
        : "";
      var title = group.querySelector(".group-title").textContent;
      var chip = el("button", "summary-chip", prefix + title + " · " + I18N.formatNumber(locale, Number(group.dataset.total)));
      chip.type = "button";
      chip.addEventListener("click", function () {
        var calm = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        group.scrollIntoView({ behavior: calm ? "auto" : "smooth", block: "start" });
      });
      nav.appendChild(chip);
    });
    results.insertBefore(nav, results.children[1] || null);
  }

  function notice(title, body, className) {
    var box = el("div", className || "empty");
    box.appendChild(el("strong", null, title));
    box.appendChild(document.createTextNode(body));
    return box;
  }

  function renderSkeleton() {
    results.innerHTML = "";
    for (var i = 0; i < 3; i++) {
      var card = el("article", "card skeleton");
      for (var j = 0; j < 4; j++) card.appendChild(el("div", "line"));
      results.appendChild(card);
    }
  }

  // --- Language switching ------------------------------------------------------

  function applyStaticTranslations() {
    document.documentElement.lang = locale;
    document.documentElement.dir = DIR[locale];
    document.title = t(locale, "doc.title");
    document.getElementById("meta-description").setAttribute("content", t(locale, "meta.description"));

    // An element may carry a second key, "data-i18n-text", used instead of
    // "data-i18n" while the search is in text mode.
    var textAttr = mode === "text" ? "data-i18n-text" : "data-i18n";
    var nodes = document.querySelectorAll("[data-i18n]");
    for (var i = 0; i < nodes.length; i++) {
      var key = nodes[i].getAttribute(nodes[i].hasAttribute(textAttr) ? textAttr : "data-i18n");
      nodes[i].textContent = t(locale, key);
    }
    var ariaNodes = document.querySelectorAll("[data-i18n-aria-label]");
    for (var j = 0; j < ariaNodes.length; j++) {
      ariaNodes[j].setAttribute("aria-label", t(locale, ariaNodes[j].getAttribute("data-i18n-aria-label")));
    }

    labelNiqqudKeys();

    input.placeholder = mode === "text"
      ? t(locale, "search.placeholder.text")
      : t(locale, "search.placeholder", { example: I18N.PLACEHOLDER_EXAMPLE });

    var modeButtons = modeSwitch.querySelectorAll(".mode-btn");
    for (var m = 0; m < modeButtons.length; m++) {
      var isMode = modeButtons[m].dataset.mode === mode;
      modeButtons[m].classList.toggle("active", isMode);
      modeButtons[m].setAttribute("aria-pressed", isMode ? "true" : "false");
    }
    examplesName.hidden = mode !== "name";
    examplesText.hidden = mode !== "text";
    anyOrderLabel.hidden = mode !== "text";
    niqqudBox.hidden = mode !== "text";
    if (mode !== "text") setNiqqudPadOpen(false);

    if (readerBooks) populateReaderBooks();
    syncReaderCommentaries();
    if (readerBooks) syncReaderTools();
    if (searchToolsReady) syncSearchTools();
    if (searchToolsReady) setStaticToolLabels();
    if (readerData) renderReaderChapter(readerData);

    document.getElementById("footer-attribution").innerHTML = t(locale, "footer.attributionHtml");

    var buttons = langSwitch.querySelectorAll(".lang-btn");
    for (var k = 0; k < buttons.length; k++) {
      var isActive = buttons[k].dataset.lang === locale;
      buttons[k].classList.toggle("active", isActive);
      buttons[k].setAttribute("aria-pressed", isActive ? "true" : "false");
    }
  }

  function setLocale(next) {
    if (!I18N.isSupported(next) || next === locale) return;
    locale = next;
    saveLocale(locale);
    applyStaticTranslations();
    installHint.hidden = true;
    // Redraw the current results in the new language without a network
    // round-trip -- the data itself doesn't change, only its labels.
    if (lastSearchData) render(lastSearchData);
  }

  langSwitch.addEventListener("click", function (event) {
    var button = event.target.closest(".lang-btn");
    if (button) setLocale(button.dataset.lang);
  });

  // --- Settings dialog ---------------------------------------------------------
  //
  // Holds the language switcher (moved out of the header banner). Native
  // <dialog>: focus trapping, Escape-to-close, and the ::backdrop all come
  // for free, same pattern as shas-radar's AI settings dialog.

  function openSettings() {
    if (typeof settingsDialog.showModal === "function") {
      settingsDialog.showModal();
    } else {
      settingsDialog.setAttribute("open", ""); // very old browser: falls back to non-modal
    }
  }

  settingsBtn.addEventListener("click", openSettings);

  // --- Install (Add to Home Screen) ---------------------------------------
  //
  // Lives in Settings and is shown whenever the app isn't already running
  // standalone. `beforeinstallprompt` is unreliable (engagement heuristics,
  // non-Chrome browsers, in-app webviews), so a tap always does something:
  // the native prompt if captured, otherwise an inline how-to for the browser.
  // The hint is inline rather than a toast because the modal dialog sits above it.

  var deferredInstallPrompt = null;

  function isStandalone() {
    return window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true;
  }

  function isIOS() {
    return /iphone|ipad|ipod/i.test(navigator.userAgent) && !window.MSStream;
  }

  if (!isStandalone()) installSection.hidden = false;

  window.addEventListener("beforeinstallprompt", function (event) {
    event.preventDefault();
    deferredInstallPrompt = event;
  });

  installBtn.addEventListener("click", function () {
    if (deferredInstallPrompt) {
      var prompt = deferredInstallPrompt;
      deferredInstallPrompt = null;
      prompt.prompt();
      prompt.userChoice
        .then(function (choice) {
          if (choice.outcome === "accepted") installSection.hidden = true;
        })
        .catch(function () { /* left visible -- tapping again just retries */ });
      return;
    }
    installHint.textContent = t(locale, isIOS() ? "install.iosHint" : "install.genericHint");
    installHint.hidden = false;
  });

  window.addEventListener("appinstalled", function () {
    installSection.hidden = true;
    deferredInstallPrompt = null;
  });

  // --- Searching -------------------------------------------------------------

  /*
   * Back to a blank page, and to the bare URL.
   *
   * A search puts its query in the hash so results can be shared and the back
   * button steps between them -- which also means the URL stays "dirty" after
   * one, and reloading or bookmarking re-runs the old search. Clearing drops
   * the hash with replaceState rather than pushState, so it tidies the address
   * bar without adding a history entry of its own (pressing Back still returns
   * to the previous search rather than to an empty page you just left).
   */
  // `refocus === false` is for callers (a tab switch) that must not raise the
  // phone keyboard; the clear button itself still returns focus to the box.
  function clearSearch(refocus) {
    if (inFlight) {
      inFlight.abort();
      inFlight = null;
    }
    input.value = "";
    lastSearchData = null;
    searchShowingSaved = false;
    syncSearchSaveButton();
    results.innerHTML = "";
    results.setAttribute("aria-busy", "false");
    submit.disabled = false;
    // The held-back verses were keyed by groups that no longer exist.
    pending = Object.create(null);
    searchHash = "";
    history.replaceState(null, "", location.pathname + location.search);
    syncClearButton();
    if (refocus !== false) input.focus();
  }

  // Only offered when there is something to clear, so it never sits there as
  // dead weight on a first visit.
  function syncClearButton() {
    clearBtn.hidden = !input.value && !results.firstChild;
  }

  // The query lives in the URL hash, so results are shareable and the back
  // button moves between searches. "#q=" is a name search (and always was, so
  // old links keep working); "#t=" is a text search, with "&any=1" when the
  // words may appear in any order.
  function toHash(query) {
    if (mode === "name") return "#q=" + encodeURIComponent(query);
    return "#t=" + encodeURIComponent(query) + (anyOrder ? "&any=1" : "");
  }

  function fromHash() {
    var match = /^#q=(.*)$/.exec(location.hash);
    var state = null;
    if (match) state = { mode: "name", query: match[1], anyOrder: false };
    match = /^#t=([^&]*)(&any=1)?$/.exec(location.hash);
    if (match) state = { mode: "text", query: match[1], anyOrder: Boolean(match[2]) };
    if (!state) return null;
    try {
      state.query = decodeURIComponent(state.query);
    } catch (err) {
      return null; // a mangled link is treated as no link
    }
    return state;
  }

  function searchPath(query) {
    if (mode === "name") return "/api/search?names=" + encodeURIComponent(query);
    return "/api/phrase?q=" + encodeURIComponent(query) + "&ordered=" + (anyOrder ? "false" : "true");
  }

  function runSearch(query, pushHash) {
    query = (query || "").trim();
    if (!query) {
      input.focus();
      return;
    }

    input.value = query;
    showView("search");
    searchHash = toHash(query);
    if (pushHash !== false) {
      if (location.hash !== searchHash) history.pushState(null, "", searchHash);
    }

    if (inFlight) inFlight.abort();
    var controller = new AbortController();
    inFlight = controller;
    searchShowingSaved = false;

    submit.disabled = true;
    results.setAttribute("aria-busy", "true");
    renderSkeleton();
    var disarmWaking = armWaking();

    apiFetch(searchPath(query), { signal: controller.signal })
      .then(function (response) {
        // A server that predates /api/phrase answers 404 with a body that is not
        // this API's error shape (or not JSON at all), so a failed parse is
        // treated as an empty body rather than thrown.
        return response.json().catch(function () { return {}; }).then(function (body) {
          if (!response.ok) {
            var unavailable = response.status === 404 && mode === "text" ? t(locale, "error.textUnavailable") : null;
            var message = (body.code && t(locale, "error.code." + body.code)) || body.error || unavailable || t(locale, "error.generic");
            throw new Error(message);
          }
          return body;
        });
      })
      .then(function (data) {
        lastSearchData = data;
        lastSearchQuery = query;
        lastSearchMode = mode;
        lastSearchAnyOrder = anyOrder;
        render(data);
        rememberRecentSearch();
        syncSearchSaveButton();
        results.scrollIntoView({ behavior: "smooth", block: "start" });
      })
      .catch(function (error) {
        if (error.name === "AbortError") return; // superseded by a newer search
        lastSearchData = null;
        syncSearchSaveButton();
        results.innerHTML = "";
        results.appendChild(notice(t(locale, "error.title"), error.message, "error"));
      })
      .then(function () {
        if (inFlight === controller) {
          inFlight = null;
          submit.disabled = false;
          results.setAttribute("aria-busy", "false");
        }
        disarmWaking();
        syncClearButton();
      });
  }

  // --- Tap a word to search it ---------------------------------------------------
  //
  // A verse in the results can be tapped: the word under the finger is searched
  // as text, with its niqqud, so there is no need to type vowels. The verse's DOM
  // is left as the server's highlights built it (text nodes split around
  // <mark>), so the tapped point is mapped back to an offset in the verse's
  // plain text instead of wrapping every word in its own element.

  // Letters and niqqud. Maqaf, paseq and sof pasuq are left out, so they end a word.
  var WORD_CHAR = /[\u05D0-\u05EA\u0591-\u05BD\u05BF\u05C1\u05C2\u05C4\u05C5\u05C7]/;
  // Cantillation: shown in the verse, not typed into the search box.
  var CANTILLATION = /[\u0591-\u05AF\u05BD\u05C0\u05C3-\u05C6]/g;

  function caretAt(x, y) {
    if (document.caretPositionFromPoint) {
      var pos = document.caretPositionFromPoint(x, y);
      return pos ? { node: pos.offsetNode, offset: pos.offset } : null;
    }
    if (document.caretRangeFromPoint) {
      var range = document.caretRangeFromPoint(x, y);
      return range ? { node: range.startContainer, offset: range.startOffset } : null;
    }
    return null;
  }

  function textOffsetIn(container, node, offset) {
    if (node.nodeType !== Node.TEXT_NODE || !container.contains(node)) return -1;
    var walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
    var before = 0;
    while (walker.nextNode()) {
      if (walker.currentNode === node) return before + offset;
      before += walker.currentNode.nodeValue.length;
    }
    return -1;
  }

  function wordAt(text, offset) {
    var start = offset;
    var end = offset;
    while (start > 0 && WORD_CHAR.test(text.charAt(start - 1))) start--;
    while (end < text.length && WORD_CHAR.test(text.charAt(end))) end++;
    return text.slice(start, end);
  }

  function searchTappedWord(word) {
    if (mode !== "text") {
      mode = "text";
      applyStaticTranslations();
    }
    anyOrder = false;
    anyOrderBox.checked = false;
    runSearch(word);
  }

  results.addEventListener("click", function (event) {
    var verse = event.target.closest(".verse");
    if (!verse) return;
    var selection = window.getSelection();
    if (selection && !selection.isCollapsed) return; // selecting text to copy, not tapping
    var caret = caretAt(event.clientX, event.clientY);
    if (!caret) return;
    var at = textOffsetIn(verse, caret.node, caret.offset);
    if (at < 0) return;
    var word = wordAt(verse.textContent, at).replace(CANTILLATION, "");
    if (word) searchTappedWord(word);
  });

  // --- Niqqud keys -----------------------------------------------------------
  //
  // Most keyboards have no easy way to type vowels, so the text mode offers a
  // row of keys that insert one at the caret, after the letter just typed. The
  // names are the Hebrew terms and are not translated, like the verse text. The
  // server normalizes the order of marks on a letter, so a dagesh typed before
  // or after a vowel finds the same verses.

  // [mark, key suffix of its `niqqud.name.*` label in i18n.js]
  var NIQQUD_KEYS = [
    ["\u05B0", "B0"], ["\u05B1", "B1"], ["\u05B2", "B2"], ["\u05B3", "B3"],
    ["\u05B4", "B4"], ["\u05B5", "B5"], ["\u05B6", "B6"], ["\u05B7", "B7"],
    ["\u05B8", "B8"], ["\u05B9", "B9"], ["\u05BB", "BB"], ["\u05BC", "BC"],
    ["\u05C1", "C1"], ["\u05C2", "C2"],
  ];
  var DOTTED_CIRCLE = "\u25CC";
  var niqqudNames = [];

  NIQQUD_KEYS.forEach(function (key) {
    var button = el("button", "niqqud-key");
    button.type = "button";
    button.dataset.mark = key[0];
    button.appendChild(el("span", "niqqud-glyph", DOTTED_CIRCLE + key[0]));
    var name = el("span", "niqqud-name");
    button.appendChild(name);
    niqqudNames.push([button, name, key[1]]);
    niqqudPad.appendChild(button);
  });

  // The mark's name is shown under it, so a key is never only a shape to guess.
  function labelNiqqudKeys() {
    niqqudNames.forEach(function (entry) {
      var label = t(locale, "niqqud.name." + entry[2]);
      entry[1].textContent = label;
      entry[0].title = label;
      entry[0].setAttribute("aria-label", label);
    });
  }

  function setNiqqudPadOpen(open) {
    niqqudPad.hidden = !open;
    niqqudToggle.setAttribute("aria-expanded", open ? "true" : "false");
  }

  function insertAtCaret(text) {
    var start = input.selectionStart == null ? input.value.length : input.selectionStart;
    var end = input.selectionEnd == null ? start : input.selectionEnd;
    input.value = input.value.slice(0, start) + text + input.value.slice(end);
    input.setSelectionRange(start + text.length, start + text.length);
    input.focus();
    syncClearButton();
  }

  niqqudToggle.addEventListener("click", function () {
    setNiqqudPadOpen(niqqudPad.hidden);
  });

  // Pressing a key must not take focus from the box, or the caret (and on a
  // phone the keyboard) would be lost with every vowel.
  niqqudPad.addEventListener("mousedown", function (event) {
    event.preventDefault();
  });

  niqqudPad.addEventListener("click", function (event) {
    var key = event.target.closest(".niqqud-key");
    if (key) insertAtCaret(key.dataset.mark);
  });

  // --- Wiring ----------------------------------------------------------------

  clearBtn.addEventListener("click", clearSearch);

  // Keeps the button in step while typing, not just after a search.
  input.addEventListener("input", syncClearButton);

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    input.blur(); // dismisses the on-screen keyboard so results are visible
    runSearch(input.value);
  });

  function onChipClick(event) {
    var chip = event.target.closest(".chip");
    if (chip) runSearch(chip.dataset.q);
  }
  examplesName.addEventListener("click", onChipClick);
  examplesText.addEventListener("click", onChipClick);

  /*
   * Switching what the box means. Whatever is on screen belongs to the other
   * mode (a name in the box is not a phrase, and its results are not a
   * phrase's), so the search is cleared rather than reinterpreted.
   */
  function setMode(next) {
    if (next === mode) return;
    mode = next;
    clearSearch(false);
    applyStaticTranslations();
  }

  modeSwitch.addEventListener("click", function (event) {
    var button = event.target.closest(".mode-btn");
    if (button) setMode(button.dataset.mode);
  });

  anyOrderBox.addEventListener("change", function () {
    anyOrder = anyOrderBox.checked;
    // Re-run in place only when there is a result to change.
    if (lastSearchData) runSearch(input.value);
  });

  // --- Reader ------------------------------------------------------------
  //
  // One chapter of the Tanakh read straight through (GET /api/chapter), with Rashi
  // on the verses he wrote on. The chapter being read is in the hash
  // (#/read/<book>/<chapter>[/<verse>]), so it can be linked to and the back button
  // steps between chapters; the last chapter read is remembered, and the Read tab
  // reopens it.

  var READER_POSITION_KEY = "pasuk-leshem:reader-position";
  var READER_COMMENTARIES_KEY = "pasuk-leshem:reader-commentaries";
  // Before there were several commentaries this was one on/off switch for Rashi.
  var READER_RASHI_KEY = "pasuk-leshem:reader-rashi";

  var viewTabs = document.getElementById("view-tabs");
  var readerEl = document.getElementById("reader");
  var readerBookSelect = document.getElementById("reader-book");
  var readerChapterSelect = document.getElementById("reader-chapter");
  var readerCommentariesEl = document.getElementById("reader-commentaries");
  var readerCommentariesPanel = document.getElementById("reader-commentaries-panel");
  var readerPageEl = document.getElementById("reader-page");
  var readerCitationEl = document.getElementById("reader-citation");
  var readerToolsEl = document.getElementById("reader-tools");
  var readerSaveBtn = document.getElementById("reader-save");
  var readerDownloadBtn = document.getElementById("reader-download");
  var readerSavedEl = document.getElementById("reader-saved");
  var readerSavedPanel = document.getElementById("reader-saved-panel");

  // GET /api/books, loaded the first time the reader opens.
  var readerBooks = null;
  var readerPosition = null; // {book, chapter, verse?} being shown
  var readerGood = null; // the last position that loaded, to fall back to when one does not
  var readerData = null; // the last /api/chapter response, kept to redraw on a language switch
  var readerRequest = 0; // a slower, older response never replaces a newer one
  var readerRender = 0; // likewise for a commentary that answers after the page was redrawn
  var readerCommentaries = []; // GET /api/books's commentaries, besides Rashi
  var readerCommentaryCache = {};
  var readerShowingSaved = false; // the page on screen is a copy kept on the device

  function loadReaderPosition() {
    try {
      var stored = JSON.parse(localStorage.getItem(READER_POSITION_KEY));
      if (stored && typeof stored.book === "string" && Number.isInteger(stored.chapter) && stored.chapter >= 1) {
        return { book: stored.book, chapter: stored.chapter };
      }
    } catch (err) {
      /* private browsing, or a value that is not JSON -- start at the beginning */
    }
    return null;
  }

  function saveReaderPosition(position) {
    try {
      localStorage.setItem(READER_POSITION_KEY, JSON.stringify({ book: position.book, chapter: position.chapter }));
    } catch (err) {
      /* the Read tab just opens at the beginning next visit */
    }
  }

  // Which commentaries the visitor ticked, by id. The old single Rashi switch is read
  // once if the new choice has not been saved yet.
  function loadReaderCommentaryChoice() {
    try {
      var stored = JSON.parse(localStorage.getItem(READER_COMMENTARIES_KEY));
      if (Array.isArray(stored)) {
        return stored.filter(function (id) { return typeof id === "string"; });
      }
      return localStorage.getItem(READER_RASHI_KEY) === "0" ? [] : ["rashi"];
    } catch (err) {
      return ["rashi"];
    }
  }

  function saveReaderCommentaryChoice(ids) {
    try {
      localStorage.setItem(READER_COMMENTARIES_KEY, JSON.stringify(ids));
    } catch (err) {
      /* the choice holds until the page is reloaded */
    }
  }

  var readerCommentaryChoice = loadReaderCommentaryChoice();

  // --- Saved chapters ----------------------------------------------------
  //
  // A chapter the visitor saves, and the last few they read, are kept in this
  // browser's IndexedDB (never sent anywhere) with the commentaries that were loaded
  // for them, so they open again with no connection. Where IndexedDB is not available
  // (some private windows) the save controls are hidden and the Read tab works as before.

  var SAVED_DB_NAME = "pasuk-leshem";
  var SAVED_STORE = "saved";
  var RECENT_LIMIT = 20;
  var savedDbPromise = null;
  var savingNow = false; // a save or un-save is in progress

  function savedDb() {
    if (savedDbPromise) return savedDbPromise;
    savedDbPromise = new Promise(function (resolve, reject) {
      if (!window.indexedDB) {
        reject(new Error("no indexedDB"));
        return;
      }
      var open = indexedDB.open(SAVED_DB_NAME, 1);
      open.onupgradeneeded = function () {
        open.result.createObjectStore(SAVED_STORE, { keyPath: "id" });
      };
      open.onsuccess = function () { resolve(open.result); };
      open.onerror = function () { reject(open.error); };
    });
    return savedDbPromise;
  }

  function savedRequest(mode, run) {
    return savedDb().then(function (db) {
      return new Promise(function (resolve, reject) {
        var transaction = db.transaction(SAVED_STORE, mode);
        var request = run(transaction.objectStore(SAVED_STORE));
        transaction.oncomplete = function () { resolve(request && request.result); };
        transaction.onerror = function () { reject(transaction.error); };
        transaction.onabort = function () { reject(transaction.error); };
      });
    });
  }

  function savedAll() {
    return savedRequest("readonly", function (store) { return store.getAll(); });
  }

  function savedPut(item) {
    return savedRequest("readwrite", function (store) { return store.put(item); });
  }

  function savedDelete(id) {
    return savedRequest("readwrite", function (store) { return store.delete(id); });
  }

  function savedKey(data) {
    return data.book.he + "|" + data.chapter;
  }

  // The commentaries loaded so far for this chapter, to keep beside it.
  function loadedCommentariesFor(data) {
    var found = {};
    readerCommentaryList().forEach(function (commentary) {
      var cached = readerCommentaryCache[commentary.id + "|" + data.book.he + "|" + data.chapter];
      if (cached) found[commentary.id] = cached;
    });
    return found;
  }

  // One chapter as it is kept: `kept` is true for one the visitor saved, false for one
  // only remembered as recently read.
  function savedItem(data, kept) {
    var loaded = loadedCommentariesFor(data);
    return {
      id: savedKey(data),
      kind: "chapter",
      kept: kept,
      title: data.ref,
      savedAt: Date.now(),
      data: data,
      commentaries: loaded,
      commentaryList: readerCommentaryList().filter(function (commentary) { return loaded[commentary.id]; }),
    };
  }

  // The newer commentaries over the ones already kept, so reading a saved page again can
  // only add to its saved copy.
  function mergedCommentaries(kept, loaded) {
    var merged = {};
    Object.keys(kept || {}).forEach(function (id) { merged[id] = kept[id]; });
    Object.keys(loaded || {}).forEach(function (id) { merged[id] = loaded[id]; });
    return merged;
  }

  // Forget the oldest of the merely recent chapters, and of the merely recent searches, past
  // RECENT_LIMIT of each.
  function pruneRecent() {
    return savedRequest("readwrite", function (store) {
      var all = store.getAll();
      all.onsuccess = function () {
        ["chapter", "search"].forEach(function (kind) {
          var recent = all.result.filter(function (item) { return !item.kept && (item.kind || "chapter") === kind; });
          recent.sort(function (a, b) { return b.savedAt - a.savedAt; });
          recent.slice(RECENT_LIMIT).forEach(function (old) { store.delete(old.id); });
        });
      };
      return all;
    });
  }

  // Remember the item just read. A saved one keeps its saved state, date and commentaries
  // (new ones are added); the read and the write are one transaction, so a save made at the
  // same moment is never undone.
  function rememberRecent(data) {
    savedRequest("readwrite", function (store) {
      var read = store.get(savedKey(data));
      read.onsuccess = function () {
        var existing = read.result;
        var item = savedItem(data, existing ? existing.kept : false);
        if (existing) {
          item.commentaries = mergedCommentaries(existing.commentaries, item.commentaries);
          item.commentaryList = existing.commentaryList.length > item.commentaryList.length
            ? existing.commentaryList : item.commentaryList;
          if (existing.kept) item.savedAt = existing.savedAt;
        }
        store.put(item);
      };
      return read;
    }).then(pruneRecent).then(renderSavedList).catch(function () { /* nothing is remembered; reading is unaffected */ });
  }

  function syncSaveButton() {
    readerSaveBtn.disabled = !readerData;
    readerDownloadBtn.disabled = !readerData;
    if (!readerData) {
      readerSaveBtn.setAttribute("aria-pressed", "false");
      setSaveLabel(readerSaveBtn, false);
      return;
    }
    savedAll().then(function (items) {
      var saved = items.some(function (item) { return item.id === savedKey(readerData) && item.kept; });
      readerSaveBtn.setAttribute("aria-pressed", saved ? "true" : "false");
      setSaveLabel(readerSaveBtn, saved);
    }).catch(function () {});
  }

  // Save, or un-save, the chapter on screen, with the commentaries loaded for it.
  function toggleSaved() {
    if (!readerData || savingNow) return;
    savingNow = true;
    var data = readerData;
    var wasSaved = readerSaveBtn.getAttribute("aria-pressed") === "true";
    var step = wasSaved
      ? savedPut(savedItem(data, false)).then(pruneRecent)
      : Promise.all(readerCommentaryList().filter(function (commentary) {
        return commentary.id !== "rashi" && readerCommentaryChoice.indexOf(commentary.id) !== -1;
      }).map(function (commentary) {
        return loadReaderCommentary(commentary.id, data).catch(function () { return null; });
      })).then(function () { return savedPut(savedItem(data, true)); });
    step.then(function () {
      syncSaveButton();
      renderSavedList();
    }).catch(function () {
      flashFailed(readerSaveBtn, "reader.saveFailed", syncSaveButton);
    }).then(function () { savingNow = false; });
  }

  // Show a kept chapter from the device, whether or not there is a connection.
  function openSaved(item) {
    // The commentary list is not there when the server cannot be reached: use the saved one.
    if (!readerCommentaries.length) {
      readerCommentaries = (item.commentaryList || []).filter(function (commentary) { return commentary.id !== "rashi"; });
    }
    Object.keys(item.commentaries || {}).forEach(function (id) {
      readerCommentaryCache[id + "|" + item.data.book.he + "|" + item.data.chapter] = item.commentaries[id];
    });
    readerRequest++;
    readerShowingSaved = true;
    readerPosition = { book: item.data.book.he, chapter: item.data.chapter };
    readerData = item.data;
    if (readerBooks) syncReaderPickers(); // the book list is not there when the server cannot be reached
    renderReaderChapter(item.data);
    syncSaveButton();
    readerPageEl.setAttribute("aria-busy", "false");
    history.pushState(null, "", readerHash(readerPosition));
    readerSavedEl.open = false;
    readerEl.scrollIntoView({ block: "start" });
  }

  // An icon button has no text of its own: its label is for screen readers and a tooltip.
  function setToolLabel(button, key) {
    var label = t(locale, key);
    button.setAttribute("aria-label", label);
    button.title = label;
  }

  // Say a tool failed for a few seconds, then run `restore` to put its label back.
  // The message is also a toast: a tooltip does not show on a phone, and a colour is not enough.
  function flashFailed(button, key, restore) {
    setToolLabel(button, key);
    toast(t(locale, key));
    button.classList.add("failed");
    clearTimeout(button.failedTimer);
    button.failedTimer = setTimeout(function () {
      button.classList.remove("failed");
      if (restore) restore();
    }, 3000);
  }

  // The save button's name stays "Save" and aria-pressed says whether it is saved; the
  // tooltip says which.
  function setSaveLabel(button, saved) {
    button.setAttribute("aria-label", t(locale, "reader.save"));
    button.title = t(locale, saved ? "reader.saved" : "reader.save");
  }

  // The labels of the buttons whose text never changes, in the current language.
  function setStaticToolLabels() {
    [[readerDownloadBtn, readerSavedEl], [searchDownloadBtn, searchSavedEl]].forEach(function (pair) {
      setToolLabel(pair[0], "reader.download");
      setToolLabel(pair[1].querySelector("summary"), "reader.savedList");
    });
  }

  // The badge on a saved list: how many items of this kind the visitor saved.
  function setSavedCount(badge, items, kind) {
    var count = items.filter(function (item) { return item.kept && (item.kind || "chapter") === kind; }).length;
    badge.textContent = String(count);
    badge.hidden = count === 0;
  }

  // The saved items of one kind, "Saved" then "Recently read", into a panel.
  function fillSavedPanel(panel, badge, items, kind, open, refresh) {
    panel.textContent = "";
    setSavedCount(badge, items, kind);
    var groups = [
      ["reader.savedHeading", true],
      [kind === "search" ? "reader.recentSearchesHeading" : "reader.recentHeading", false],
    ];
    var any = false;
    groups.forEach(function (group) {
      var chosen = items.filter(function (item) {
        return (item.kind || "chapter") === kind && item.kept === group[1];
      });
      chosen.sort(function (a, b) { return b.savedAt - a.savedAt; });
      if (!chosen.length) return;
      any = true;
      panel.appendChild(el("p", "reader-saved-heading", t(locale, group[0])));
      chosen.forEach(function (item) {
        var row = el("div", "reader-saved-row");
        var opener = hebrewSpan("button", "reader-saved-open", item.title);
        opener.type = "button";
        opener.addEventListener("click", function () { open(item); });
        var remove = el("button", "reader-saved-remove", "✕");
        remove.type = "button";
        remove.setAttribute("aria-label", t(locale, "reader.delete"));
        remove.addEventListener("click", function () {
          savedDelete(item.id).then(refresh).catch(function () {
            remove.textContent = "!"; // the row is still there: the delete did not happen
          });
        });
        row.appendChild(opener);
        row.appendChild(remove);
        panel.appendChild(row);
      });
    });
    if (!any) panel.appendChild(el("p", "reader-saved-heading", t(locale, "reader.savedEmpty")));
  }

  function renderSavedList() {
    savedAll().then(function (items) {
      fillSavedPanel(readerSavedPanel, readerSavedEl.querySelector(".badge"), items, "chapter", openSaved, function () { renderSavedList(); syncSaveButton(); });
    }).catch(function () {});
  }

  // --- Downloading what is on screen ---------------------------------------

  var DOWNLOAD_FALLBACK_CSS =
    "body{font-family:serif;max-width:46rem;margin:1rem auto;padding:0 1rem;line-height:1.9}" +
    ".reader-verse{display:flex;gap:.6rem}.reader-verse-num{flex:0 0 1.9rem;font-weight:700}";

  function downloadFile(name, html) {
    var link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob([html], { type: "text/html;charset=utf-8" }));
    link.download = name;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(function () { URL.revokeObjectURL(link.href); }, 10000);
  }

  // The chapter as the visitor sees it (the notes they opened and the ones they did not,
  // all open) in one self-contained .html file, styled with the app's own stylesheet.
  function downloadReaderPage() {
    if (!readerData) return;
    // An English name: a Hebrew file name is lost in some browsers' downloads.
    var fileName = readerData.book.en.replace(/[^A-Za-z0-9]+/g, "_") + "_" + readerData.chapter + ".html";
    downloadPage(readerPageEl, readerData.ref, fileName, readerDownloadBtn);
  }

  // `source`'s content as a file, with its title; `button` shows if that fails.
  // With `plain`, the buttons and boxes in it are dropped: they do nothing in a file.
  function downloadPage(source, title, fileName, button, plain) {
    fetch("styles.css").then(function (response) {
      if (!response.ok) throw new Error("css " + response.status);
      return response.text();
    }).catch(function () { return DOWNLOAD_FALLBACK_CSS; }).then(function (css) {
      var doc = document.implementation.createHTMLDocument(title);
      doc.documentElement.lang = locale;
      doc.documentElement.dir = "rtl";
      doc.head.appendChild(doc.createElement("meta")).setAttribute("charset", "utf-8");
      doc.head.appendChild(doc.createElement("style")).textContent = css;
      var page = source.cloneNode(true);
      page.removeAttribute("id");
      page.hidden = false;
      if (plain) page.querySelectorAll("button, input").forEach(function (control) { control.remove(); });
      page.querySelectorAll("details").forEach(function (details) { details.setAttribute("open", ""); });
      // The title lives beside the page, not in it: put it back above, in the card it sat in.
      var card = doc.createElement("div");
      card.className = "reader-card";
      var h2 = doc.createElement("h2");
      h2.className = "reader-citation";
      h2.textContent = title;
      card.appendChild(h2);
      card.appendChild(page);
      doc.body.appendChild(card);
      downloadFile(fileName, "<!doctype html>\n" + doc.documentElement.outerHTML);
    }).catch(function () {
      flashFailed(button, "reader.downloadFailed", function () { setToolLabel(button, "reader.download"); });
    });
  }

  // --- Saved searches ----------------------------------------------------
  //
  // The same for the Search tab: the results on screen can be saved, are remembered as recent,
  // and download as a file. A search is kept as the response it got, so it shows again with no
  // connection.

  var savingSearch = false; // a save or un-save of the results is in progress
  var searchToolsEl = document.getElementById("search-tools");
  var searchSaveBtn = document.getElementById("search-save");
  var searchDownloadBtn = document.getElementById("search-download");
  var searchSavedEl = document.getElementById("search-saved");
  var searchSavedPanel = document.getElementById("search-saved-panel");
  var searchTitleEl = document.getElementById("search-title");
  var searchToolsReady = false;

  function searchItem(kept) {
    var query = lastSearchQuery;
    return {
      id: "search|" + lastSearchMode + "|" + (lastSearchAnyOrder ? 1 : 0) + "|" + query,
      kind: "search",
      kept: kept,
      title: query,
      savedAt: Date.now(),
      query: query,
      mode: lastSearchMode,
      anyOrder: lastSearchAnyOrder,
      data: lastSearchData,
    };
  }

  // Remember the results just shown, as a recent search; a saved one keeps its saved state and
  // date.
  function rememberRecentSearch() {
    if (!lastSearchData) return;
    var fresh = searchItem(false);
    savedRequest("readwrite", function (store) {
      var read = store.get(fresh.id);
      read.onsuccess = function () {
        if (read.result) {
          fresh.kept = read.result.kept;
          if (read.result.kept) fresh.savedAt = read.result.savedAt;
        }
        store.put(fresh);
      };
      return read;
    }).then(pruneRecent).then(renderSearchSavedList).catch(function () { /* nothing is remembered */ });
  }

  function renderSearchSavedList() {
    savedAll().then(function (items) {
      fillSavedPanel(searchSavedPanel, searchSavedEl.querySelector(".badge"), items, "search", openSavedSearch, function () {
        renderSearchSavedList();
        syncSearchSaveButton();
      });
    }).catch(function () {});
  }

  function syncSearchSaveButton() {
    if (!searchToolsReady) return;
    searchTitleEl.textContent = lastSearchQuery;
    searchTitleEl.hidden = !lastSearchQuery;
    searchSaveBtn.disabled = !lastSearchData;
    searchDownloadBtn.disabled = !lastSearchData;
    if (!lastSearchData) {
      searchSaveBtn.setAttribute("aria-pressed", "false");
      setSaveLabel(searchSaveBtn, false);
      return;
    }
    var id = searchItem(false).id;
    savedAll().then(function (items) {
      var saved = items.some(function (item) { return item.id === id && item.kept; });
      searchSaveBtn.setAttribute("aria-pressed", saved ? "true" : "false");
      setSaveLabel(searchSaveBtn, saved);
    }).catch(function () {});
  }

  // Save, or un-save, the results on screen. Whether it is saved already is read in the same
  // transaction as the write, not taken from the button, which may not have caught up.
  function toggleSavedSearch() {
    if (!lastSearchData || inFlight || savingSearch) return;
    savingSearch = true;
    var fresh = searchItem(true);
    savedRequest("readwrite", function (store) {
      var read = store.get(fresh.id);
      read.onsuccess = function () {
        var wasSaved = Boolean(read.result && read.result.kept);
        fresh.kept = !wasSaved;
        store.put(fresh);
      };
      return read;
    }).then(pruneRecent).then(function () {
      syncSearchSaveButton();
      renderSearchSavedList();
    }).catch(function () {
      flashFailed(searchSaveBtn, "reader.saveFailed", syncSearchSaveButton);
    }).then(function () { savingSearch = false; });
  }

  // Show kept results from the device, whether or not there is a connection.
  function openSavedSearch(item) {
    if (inFlight) inFlight.abort();
    showView("search");
    mode = item.mode;
    anyOrder = item.anyOrder;
    anyOrderBox.checked = anyOrder;
    applyStaticTranslations();
    input.value = item.query;
    lastSearchData = item.data;
    lastSearchQuery = item.query;
    lastSearchMode = item.mode;
    lastSearchAnyOrder = item.anyOrder;
    searchShowingSaved = true;
    // No "#q=": back, forward or a reload would run that search live and replace the saved copy.
    searchHash = "";
    history.pushState(null, "", location.pathname + location.search);
    render(item.data);
    results.setAttribute("aria-busy", "false");
    searchSavedEl.open = false;
    syncSearchSaveButton();
    syncClearButton();
    results.scrollIntoView({ block: "start" });
  }

  function downloadSearch() {
    if (!lastSearchData || inFlight) return;
    var now = new Date();
    var pad = function (n) { return (n < 10 ? "0" : "") + n; };
    var stamp = now.getFullYear() + pad(now.getMonth() + 1) + pad(now.getDate()) + "_" + pad(now.getHours()) + pad(now.getMinutes());
    downloadPage(results, lastSearchQuery, "search_" + stamp + ".html", searchDownloadBtn, true);
  }

  function syncSearchTools() {
    savedDb().then(function () {
      searchToolsReady = true;
      searchToolsEl.hidden = false;
      setToolLabel(searchDownloadBtn, "reader.download");
      setToolLabel(searchSavedEl.querySelector("summary"), "reader.savedList");
      renderSearchSavedList();
      syncSearchSaveButton();
    }).catch(function () { searchToolsEl.hidden = true; });
  }

  searchSaveBtn.addEventListener("click", toggleSavedSearch);
  searchDownloadBtn.addEventListener("click", downloadSearch);
  document.addEventListener("click", function (event) {
    if (!event.target.closest("#search-saved")) searchSavedEl.open = false;
  });
  syncSearchTools();

  function syncReaderTools() {
    savedDb().then(function () {
      readerToolsEl.hidden = false;
      setToolLabel(readerDownloadBtn, "reader.download");
      setToolLabel(readerSavedEl.querySelector("summary"), "reader.savedList");
      renderSavedList();
      syncSaveButton();
    }).catch(function () { readerToolsEl.hidden = true; });
  }

  // Rashi comes with the chapter; the others are fetched, and listed by /api/books.
  function readerCommentaryList() {
    return [{ id: "rashi", he: "רש״י", en: "Rashi", fr: "Rachi" }].concat(readerCommentaries);
  }

  function commentaryName(commentary) {
    return commentary[locale] || commentary.he;
  }

  function syncReaderCommentaries() {
    readerCommentariesPanel.textContent = "";
    readerCommentaryList().forEach(function (commentary) {
      var option = el("label", "reader-commentary-option");
      var box = document.createElement("input");
      box.type = "checkbox";
      box.value = commentary.id;
      box.checked = readerCommentaryChoice.indexOf(commentary.id) !== -1;
      option.appendChild(box);
      option.appendChild(el("span", null, commentaryName(commentary)));
      readerCommentariesPanel.appendChild(option);
    });
  }

  // One commentary's text on the chapter being read, from the cache or the network.
  function loadReaderCommentary(id, data) {
    var key = id + "|" + data.book.he + "|" + data.chapter;
    if (readerCommentaryCache[key]) return Promise.resolve(readerCommentaryCache[key]);
    var params = new URLSearchParams({ book: data.book.he, chapter: String(data.chapter), commentary: id });
    return apiFetch("/api/commentary?" + params.toString()).then(function (response) {
      if (!response.ok) throw new Error("commentary " + response.status);
      return response.json();
    }).then(function (loaded) {
      readerCommentaryCache[key] = loaded;
      return loaded;
    });
  }

  // A commentary's note under a verse, among that verse's other notes in the order the
  // commentaries are listed, whichever answered first. Its text is limited at build time
  // to <b>/<small>/<br> (scripts/build_dataset.py's clean_rashi_comment), as Rashi's is.
  function insertCommentaryNote(body, commentary, text, order) {
    var details = el("details", "rashi");
    details.dataset.order = String(order);
    details.appendChild(el("summary", null, commentaryName(commentary)));
    var content = hebrewSpan("div", "rashi-text", null);
    content.innerHTML = text;
    details.appendChild(content);
    var later = null;
    body.querySelectorAll("details").forEach(function (note) {
      if (!later && Number(note.dataset.order) > order) later = note;
    });
    body.insertBefore(details, later);
  }

  // The ticked commentaries other than Rashi, fetched one by one for the page just drawn.
  function showReaderCommentaries(data, bodies) {
    var render = ++readerRender;
    readerCommentaryList().forEach(function (commentary, order) {
      if (commentary.id === "rashi" || readerCommentaryChoice.indexOf(commentary.id) === -1) return;
      var name = commentaryName(commentary);
      var status = el("p", "attribution", t(locale, "reader.commentaryLoading", { name: name }));
      readerPageEl.appendChild(status);
      loadReaderCommentary(commentary.id, data).then(function (loaded) {
        if (render !== readerRender) return;
        loaded.verses.forEach(function (verse) {
          if (bodies[verse.verse]) insertCommentaryNote(bodies[verse.verse], commentary, verse.text, order);
        });
        if (readerData === data) rememberRecent(data);
        status.textContent = !loaded.verses.length
          ? t(locale, "reader.commentaryNone", { name: name })
          : loaded.license ? t(locale, "reader.commentaryCredit", { name: name, license: loaded.license }) : "";
        status.hidden = !status.textContent;
      }).catch(function () {
        if (render === readerRender) status.textContent = t(locale, "reader.commentaryError", { name: name });
      });
    });
  }

  function readerHash(position) {
    return "#/read/" + encodeURIComponent(position.book) + "/" + position.chapter +
      (position.verse ? "/" + position.verse : "");
  }

  function readerPositionFromHash() {
    var match = /^#\/read\/([^/]+)\/(\d+)(?:\/(\d+))?$/.exec(location.hash);
    if (!match) return null;
    try {
      var position = { book: decodeURIComponent(match[1]), chapter: Number(match[2]) };
      if (match[3]) position.verse = Number(match[3]);
      return position;
    } catch (err) {
      return null; // a malformed %-escape
    }
  }

  function readerBookInfo(he) {
    if (!readerBooks) return null;
    for (var i = 0; i < readerBooks.length; i++) {
      if (readerBooks[i].he === he) return readerBooks[i];
    }
    return null;
  }

  // A link from a search result to its verse in the chapter.
  function readerLink(verse) {
    var position = { book: verse.book.he, chapter: verse.chapter, verse: verse.verse };
    var link = el("a", "copy", t(locale, "reader.openInReader"));
    link.href = readerHash(position);
    link.addEventListener("click", function (event) {
      event.preventDefault();
      openReader(position, true);
    });
    return link;
  }

  function showView(name) {
    var reading = name === "read";
    form.hidden = reading;
    results.hidden = reading;
    searchHeadEl.hidden = reading;
    readerEl.hidden = !reading;
    viewTabs.querySelectorAll(".view-tab").forEach(function (tab) {
      var active = tab.dataset.view === name;
      tab.classList.toggle("active", active);
      tab.setAttribute("aria-pressed", active ? "true" : "false");
    });
  }

  function populateReaderBooks() {
    readerBookSelect.textContent = "";
    readerBooks.forEach(function (book) {
      var option = document.createElement("option");
      option.value = book.he;
      option.textContent = book[locale] || book.he;
      readerBookSelect.appendChild(option);
    });
    syncReaderPickers();
  }

  function syncReaderPickers() {
    if (!readerPosition) return;
    var info = readerBookInfo(readerPosition.book);
    readerBookSelect.value = readerPosition.book;
    readerChapterSelect.textContent = "";
    if (!info) return;
    for (var chapter = 1; chapter <= info.chapters; chapter++) {
      var option = document.createElement("option");
      option.value = String(chapter);
      option.textContent = locale === "he" ? info.chaptersHe[chapter - 1] : String(chapter);
      readerChapterSelect.appendChild(option);
    }
    readerChapterSelect.value = String(readerPosition.chapter);
  }

  function syncReaderNav(data) {
    readerEl.querySelectorAll(".reader-prev").forEach(function (button) {
      button.disabled = !(data && data.previous);
    });
    readerEl.querySelectorAll(".reader-next").forEach(function (button) {
      button.disabled = !(data && data.next);
    });
  }

  function renderReaderChapter(data) {
    readerPageEl.textContent = "";
    readerCitationEl.textContent = data.ref;
    if (readerShowingSaved) readerPageEl.appendChild(el("p", "attribution", t(locale, "reader.savedCopy")));
    var withRashi = readerCommentaryChoice.indexOf("rashi") !== -1;
    var bodies = {};
    data.verses.forEach(function (verse) {
      var row = el("div", "reader-verse");
      row.dataset.verse = String(verse.verse);
      row.appendChild(el("span", "reader-verse-num", locale === "he" ? verse.verseHe : String(verse.verse)));
      var body = el("div", "reader-verse-body");
      body.appendChild(hebrewSpan("p", "verse", verse.text));
      var rashi = withRashi ? rashiDisclosure(verse) : null;
      if (rashi) body.appendChild(rashi);
      bodies[verse.verse] = body;
      row.appendChild(body);
      readerPageEl.appendChild(row);
    });
    showReaderCommentaries(data, bodies);
    // Redrawn for Rashi or a language switch: keep the mark, without scrolling again.
    if (readerPosition && readerPosition.verse) markReaderTarget(readerPosition.verse);
    syncReaderNav(data);
  }

  // Mark the verse a search result linked to, so it can be found.
  function markReaderTarget(verse) {
    var row = readerPageEl.querySelector('[data-verse="' + verse + '"]');
    if (row) row.classList.add("reader-verse-target");
    return row;
  }

  // Bring that verse into view.
  function showReaderTarget(verse) {
    var row = markReaderTarget(verse);
    if (!row) return false;
    row.scrollIntoView({ block: "center" });
    return true;
  }

  function showReaderChapter(position, pushHash) {
    var request = ++readerRequest;
    readerShowingSaved = false;
    readerPosition = position;
    readerData = null;
    syncSaveButton();
    syncReaderPickers();
    syncReaderNav(null);
    if (pushHash && location.hash !== readerHash(position)) {
      history.pushState(null, "", readerHash(position));
    }

    readerCitationEl.textContent = "";
    readerPageEl.setAttribute("aria-busy", "true");
    readerPageEl.textContent = "";
    var skeleton = el("div", "skeleton");
    for (var i = 0; i < 4; i++) skeleton.appendChild(el("div", "line"));
    readerPageEl.appendChild(skeleton);
    var disarm = armWaking();

    var params = new URLSearchParams({ book: position.book, chapter: String(position.chapter) });
    apiFetch("/api/chapter?" + params.toString())
      .then(function (response) {
        return response.json().then(function (body) {
          if (!response.ok) {
            var failure = new Error("chapter " + response.status);
            failure.userMessage = body.code && t(locale, "error.code." + body.code);
            throw failure;
          }
          return body;
        }, function () {
          throw new Error("chapter " + response.status); // an error body that is not JSON
        });
      })
      .then(function (data) {
        if (request !== readerRequest) return;
        readerData = data;
        readerGood = { book: position.book, chapter: position.chapter };
        saveReaderPosition(position);
        renderReaderChapter(data);
        rememberRecent(data);
        syncSaveButton();
        if (!(position.verse && showReaderTarget(position.verse))) readerEl.scrollIntoView({ block: "start" });
      })
      .catch(function (error) {
        if (request !== readerRequest) return;
        // The pickers go back to a chapter that exists, so the Read tab and the
        // pickers can recover from a bad link.
        readerPosition = readerGood || { book: readerBooks[0].he, chapter: 1 };
        syncReaderPickers();
        readerPageEl.textContent = "";
        readerPageEl.appendChild(notice(t(locale, "error.title"), error.userMessage || t(locale, "reader.error"), "error"));
      })
      .then(function () {
        if (request === readerRequest) readerPageEl.setAttribute("aria-busy", "false");
        disarm();
      });
  }

  function ensureReaderBooks() {
    if (readerBooks) return Promise.resolve();
    var disarm = armWaking();
    return apiFetch("/api/books")
      .then(function (response) {
        if (!response.ok) throw new Error("books " + response.status);
        return response.json();
      })
      .then(function (data) {
        readerBooks = data.books;
        readerCommentaries = Array.isArray(data.commentaries) ? data.commentaries : [];
        disarm();
      }, function (error) {
        disarm();
        throw error;
      });
  }

  // `position` is where to open; without one, where the visitor left off, or the
  // first chapter of the first book.
  function openReader(position, pushHash) {
    showView("read");
    ensureReaderBooks()
      .then(function () {
        var start = position || readerPosition || loadReaderPosition() || { book: readerBooks[0].he, chapter: 1 };
        readerPosition = start;
        syncReaderCommentaries();
        syncReaderTools();
        populateReaderBooks();
        showReaderChapter(start, pushHash);
      })
      .catch(function () {
        // Without the server the saved chapters are still there to open.
        syncReaderTools();
        readerPageEl.textContent = "";
        readerPageEl.appendChild(notice(t(locale, "error.title"), t(locale, "reader.error"), "error"));
      });
  }

  function goToReaderChapter(ref) {
    showReaderChapter({ book: ref.book, chapter: ref.chapter }, true);
  }

  viewTabs.addEventListener("click", function (event) {
    var tab = event.target.closest(".view-tab");
    if (!tab) return;
    if (tab.dataset.view === "read") {
      openReader(null, true);
    } else if (!readerEl.hidden) {
      showView("search");
      history.pushState(null, "", searchHash || location.pathname + location.search);
    }
  });

  readerBookSelect.addEventListener("change", function () {
    showReaderChapter({ book: readerBookSelect.value, chapter: 1 }, true);
  });

  readerChapterSelect.addEventListener("change", function () {
    showReaderChapter({ book: readerPosition.book, chapter: Number(readerChapterSelect.value) }, true);
  });

  readerEl.addEventListener("click", function (event) {
    if (!readerData) return;
    if (event.target.closest(".reader-prev") && readerData.previous) goToReaderChapter(readerData.previous);
    if (event.target.closest(".reader-next") && readerData.next) goToReaderChapter(readerData.next);
  });

  readerSaveBtn.addEventListener("click", toggleSaved);
  readerDownloadBtn.addEventListener("click", downloadReaderPage);
  document.addEventListener("click", function (event) {
    if (!event.target.closest("#reader-saved")) readerSavedEl.open = false;
  });

  readerCommentariesPanel.addEventListener("change", function (event) {
    var id = event.target.value;
    readerCommentaryChoice = readerCommentaryChoice.filter(function (chosen) { return chosen !== id; });
    if (event.target.checked) readerCommentaryChoice.push(id);
    saveReaderCommentaryChoice(readerCommentaryChoice);
    if (readerData) renderReaderChapter(readerData);
  });

  // The dropdown closes when the visitor taps anywhere else, presses Escape, or tabs out of it.
  document.addEventListener("click", function (event) {
    if (!event.target.closest("#reader-commentaries")) readerCommentariesEl.open = false;
  });
  readerCommentariesEl.addEventListener("keydown", function (event) {
    if (event.key !== "Escape") return;
    readerCommentariesEl.open = false;
    readerCommentariesEl.querySelector("summary").focus();
  });
  readerCommentariesEl.addEventListener("focusout", function (event) {
    if (event.relatedTarget && !readerCommentariesEl.contains(event.relatedTarget)) {
      readerCommentariesEl.open = false;
    }
  });

  // Applies a mode and query that came from the URL rather than from a click.
  function runFromHash(state) {
    mode = state.mode;
    anyOrder = state.anyOrder;
    anyOrderBox.checked = anyOrder;
    applyStaticTranslations();
    runSearch(state.query, false);
  }

  window.addEventListener("popstate", function () {
    var position = readerPositionFromHash();
    if (position) {
      openReader(position, false);
      return;
    }
    showView("search");
    var state = fromHash();
    if (state) runFromHash(state);
  });

  applyStaticTranslations();

  // Registers the service worker (static/sw.js), which makes the app
  // installable to a home screen and keeps a copy of the shell so the icon
  // opens straight into the UI -- even while the API host is still waking.
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", function () {
      navigator.serviceWorker.register("/sw.js").catch(function () { /* installability just degrades gracefully */ });
    });
  }

  // Also the very first request the page makes, so a cold host is
  // explained immediately on load rather than only once the user searches.
  var disarmHealthWaking = armWaking();
  apiFetch("/api/health")
    .then(function (r) { return r.json(); })
    .catch(function () {})
    .then(disarmHealthWaking);

  var initialPosition = readerPositionFromHash();
  var initial = fromHash();
  if (initialPosition) openReader(initialPosition, false);
  else if (initial) runFromHash(initial);
})();
