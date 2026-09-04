/*
 * פסוק לשם — frontend.
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

  var t = I18N.t;
  var plural = I18N.plural;

  var LOCALE_STORAGE_KEY = "pasuk-leshem:locale";

  var form = document.getElementById("search-form");
  var input = document.getElementById("names");
  var submit = document.getElementById("submit");
  var results = document.getElementById("results");
  var toastEl = document.getElementById("toast");
  var wakingEl = document.getElementById("waking");
  var langSwitch = document.getElementById("lang-switch");

  // Verses held back behind a "show more" button, keyed by group id.
  var pending = Object.create(null);
  var groupSeq = 0;

  // Lets a new search cancel the request still in flight behind it.
  var inFlight = null;

  // The current UI language, and enough state to redraw without a network
  // round-trip when it changes: the last successful search response, and the
  // last health totals for the footer line.
  var locale = loadLocale();
  var lastSearchData = null;
  var lastHealth = null;

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
    card.appendChild(foot);

    return card;
  }

  /*
   * One result group: a heading, an optional description, the verses, and a
   * "show more" button when the group was capped.
   */
  function renderGroup(titleKey, descKey, descVars, group, note) {
    if (!group || !group.total) return null;

    var section = el("section", "group");
    var head = el("div", "group-head");
    head.appendChild(el("h3", "group-title", t(locale, titleKey)));

    var shown = group.verses.length;
    var label = shown < group.total
      ? t(locale, "count.showingOf", { shown: I18N.formatNumber(locale, shown), totalPhrase: plural(locale, "footer.verses", group.total) })
      : plural(locale, "footer.verses", group.total);
    head.appendChild(el("span", "group-count", label));
    section.appendChild(head);

    if (descKey) section.appendChild(el("p", "group-desc", t(locale, descKey, descVars)));

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

  function renderPairGroup(titleKey, descKey, descVars, pairs) {
    if (!pairs || !pairs.length) return null;

    var section = el("section", "group");
    var head = el("div", "group-head");
    head.appendChild(el("h3", "group-title", t(locale, titleKey)));
    head.appendChild(el("span", "group-count", plural(locale, "pair.matches", pairs.length)));
    section.appendChild(head);

    if (descKey) section.appendChild(el("p", "group-desc", t(locale, descKey, descVars)));
    pairs.forEach(function (pair) {
      section.appendChild(renderPair(pair));
    });
    return section;
  }

  function render(data) {
    results.innerHTML = "";
    pending = Object.create(null);

    var any = false;
    var isPair = data.query.mode === "pair";

    if (isPair) {
      var names = data.query.names;
      var pairVars = { name1: names[0], name2: names[1] };
      var groups = [
        renderPairGroup("pair.consecutive.title", "pair.consecutive.desc", pairVars, data.pairs.consecutive),
        renderPairGroup("pair.reversed.title", "pair.reversed.desc", pairVars, data.pairs.reversed),
        renderPairGroup("pair.nearMiss.title", "pair.nearMiss.desc", null, data.pairs.nearMiss),
      ];

      groups.forEach(function (group) {
        if (group) {
          results.appendChild(group);
          any = true;
        }
      });

      if (!any) {
        results.appendChild(noPairsNotice(pairVars));
      }
    }

    data.names.forEach(function (entry) {
      var header = el("div", "name-head");
      header.appendChild(hebrewSpan("h2", null, entry.name));
      header.appendChild(el("span", "name-letters", entry.first + " … " + entry.last));
      results.appendChild(header);

      var letterVars = { first: entry.first, last: entry.last };
      var groups = [
        renderGroup("group.letterMatch.title", "group.letterMatch.desc", letterVars, entry.letterMatch),
        renderGroup("group.exactWord.title", "group.exactWord.desc", null, entry.exactWord),
        renderGroup("group.partialWord.title", "group.partialWord.desc", null, entry.partialWord),
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
  }

  function notice(title, body, className) {
    var box = el("div", className || "empty");
    box.appendChild(el("strong", null, title));
    box.appendChild(document.createTextNode(body));
    return box;
  }

  /* Consecutive pairs are genuinely rare, so the empty state explains why
     rather than implying the user typed something wrong. */
  function noPairsNotice(pairVars) {
    return notice(t(locale, "pair.empty.title"), t(locale, "pair.empty.desc", pairVars));
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

    var nodes = document.querySelectorAll("[data-i18n]");
    for (var i = 0; i < nodes.length; i++) {
      nodes[i].textContent = t(locale, nodes[i].getAttribute("data-i18n"));
    }
    var ariaNodes = document.querySelectorAll("[data-i18n-aria-label]");
    for (var j = 0; j < ariaNodes.length; j++) {
      ariaNodes[j].setAttribute("aria-label", t(locale, ariaNodes[j].getAttribute("data-i18n-aria-label")));
    }

    input.placeholder = t(locale, "search.placeholder", { example: I18N.PLACEHOLDER_EXAMPLE });

    document.getElementById("footer-attribution").innerHTML = t(locale, "footer.attributionHtml");
    renderFooterCount();

    var buttons = langSwitch.querySelectorAll(".lang-btn");
    for (var k = 0; k < buttons.length; k++) {
      var isActive = buttons[k].dataset.lang === locale;
      buttons[k].classList.toggle("active", isActive);
      buttons[k].setAttribute("aria-pressed", isActive ? "true" : "false");
    }
  }

  function renderFooterCount() {
    var target = document.getElementById("verse-count");
    if (!lastHealth) {
      target.textContent = "";
      return;
    }
    target.textContent = t(locale, "footer.summary", {
      versesPhrase: plural(locale, "footer.verses", lastHealth.verses),
      booksPhrase: plural(locale, "footer.books", lastHealth.books),
    });
  }

  function setLocale(next) {
    if (!I18N.isSupported(next) || next === locale) return;
    locale = next;
    saveLocale(locale);
    applyStaticTranslations();
    // Redraw the current results in the new language without a network
    // round-trip -- the data itself doesn't change, only its labels.
    if (lastSearchData) render(lastSearchData);
  }

  langSwitch.addEventListener("click", function (event) {
    var button = event.target.closest(".lang-btn");
    if (button) setLocale(button.dataset.lang);
  });

  // --- Searching -------------------------------------------------------------

  function runSearch(query, pushHash) {
    query = (query || "").trim();
    if (!query) {
      input.focus();
      return;
    }

    input.value = query;
    if (pushHash !== false) {
      var encoded = "#q=" + encodeURIComponent(query);
      if (location.hash !== encoded) history.pushState(null, "", encoded);
    }

    if (inFlight) inFlight.abort();
    var controller = new AbortController();
    inFlight = controller;

    submit.disabled = true;
    results.setAttribute("aria-busy", "true");
    renderSkeleton();
    var disarmWaking = armWaking();

    fetch("/api/search?names=" + encodeURIComponent(query), { signal: controller.signal })
      .then(function (response) {
        return response.json().then(function (body) {
          if (!response.ok) {
            var message = (body.code && t(locale, "error.code." + body.code)) || body.error || t(locale, "error.generic");
            throw new Error(message);
          }
          return body;
        });
      })
      .then(function (data) {
        lastSearchData = data;
        render(data);
        results.scrollIntoView({ behavior: "smooth", block: "start" });
      })
      .catch(function (error) {
        if (error.name === "AbortError") return; // superseded by a newer search
        lastSearchData = null;
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
      });
  }

  // --- Wiring ----------------------------------------------------------------

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    input.blur(); // dismisses the on-screen keyboard so results are visible
    runSearch(input.value);
  });

  document.getElementById("examples").addEventListener("click", function (event) {
    var chip = event.target.closest(".chip");
    if (chip) runSearch(chip.dataset.q);
  });

  // The query lives in the URL hash, so results are shareable and the back
  // button moves between searches.
  function fromHash() {
    var match = /^#q=(.*)$/.exec(location.hash);
    return match ? decodeURIComponent(match[1]) : "";
  }

  window.addEventListener("popstate", function () {
    var query = fromHash();
    if (query) runSearch(query, false);
  });

  applyStaticTranslations();

  // Also the very first request the page makes, so a cold host is
  // explained immediately on load rather than only once the user searches.
  var disarmHealthWaking = armWaking();
  fetch("/api/health")
    .then(function (r) { return r.json(); })
    .then(function (health) {
      lastHealth = health;
      renderFooterCount();
    })
    .catch(function () { /* the footer count is decorative */ })
    .then(disarmHealthWaking);

  var initial = fromHash();
  if (initial) runSearch(initial, false);
})();
