/*
 * פסוק לשם — frontend.
 *
 * Plain ES2020, no build step and no framework. The server does the matching
 * and returns highlight offsets, so this file is only concerned with asking,
 * rendering, and the small interactions around a result (copy, show more).
 */

(function () {
  "use strict";

  var form = document.getElementById("search-form");
  var input = document.getElementById("names");
  var submit = document.getElementById("submit");
  var results = document.getElementById("results");
  var toastEl = document.getElementById("toast");

  // Verses held back behind a "show more" button, keyed by group id.
  var pending = Object.create(null);
  var groupSeq = 0;

  // Lets a new search cancel the request still in flight behind it.
  var inFlight = null;

  // --- Small helpers ---------------------------------------------------------

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  function toast(message) {
    toastEl.textContent = message;
    toastEl.classList.add("show");
    clearTimeout(toast.timer);
    toast.timer = setTimeout(function () {
      toastEl.classList.remove("show");
    }, 1900);
  }

  /* Hebrew plurals read badly with a bare number, so count phrases are built
     explicitly rather than by string interpolation. */
  function verseCount(n) {
    if (n === 1) return "פסוק אחד";
    if (n === 2) return "שני פסוקים";
    return n.toLocaleString("he-IL") + " פסוקים";
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
    var p = el("p", "verse");
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
    var button = el("button", "copy");
    button.type = "button";
    button.textContent = "העתקה";

    button.addEventListener("click", function () {
      var payload = verse.text + "\n(" + verse.ref + ")";

      function done() {
        button.textContent = "✓ הועתק";
        button.classList.add("done");
        toast("הפסוק הועתק");
        setTimeout(function () {
          button.textContent = "העתקה";
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
          toast("ההעתקה נכשלה");
        }
        document.body.removeChild(area);
      }
    });

    return button;
  }

  function verseCard(verse, note) {
    var card = el("article", "card");

    var head = el("div", "card-head");
    head.appendChild(el("span", "badge badge-book", verse.book));
    head.appendChild(el("span", "badge", "פרק " + hebrewPart(verse.ref, 0)));
    head.appendChild(el("span", "badge", "פסוק " + hebrewPart(verse.ref, 1)));
    if (note) head.appendChild(el("span", "badge badge-note", note));
    card.appendChild(head);

    card.appendChild(renderVerse(verse.text, verse.highlights));

    var foot = el("div", "card-foot");
    foot.appendChild(copyButton(verse));
    card.appendChild(foot);

    return card;
  }

  /* The server sends refs already in Hebrew numerals ("בראשית א׳:ב׳"); split
     the chapter and verse back out so each gets its own badge. */
  function hebrewPart(ref, index) {
    var tail = ref.slice(ref.lastIndexOf(" ") + 1);
    return tail.split(":")[index] || "";
  }

  /*
   * One result group: a heading, an optional description, the verses, and a
   * "show more" button when the group was capped.
   */
  function renderGroup(title, description, group, note) {
    if (!group || !group.total) return null;

    var section = el("section", "group");
    var head = el("div", "group-head");
    head.appendChild(el("h3", "group-title", title));

    var shown = group.verses.length;
    var label = shown < group.total
      ? "מציג " + shown + " מתוך " + verseCount(group.total)
      : verseCount(group.total);
    head.appendChild(el("span", "group-count", label));
    section.appendChild(head);

    if (description) section.appendChild(el("p", "group-desc", description));

    var visible = group.verses.slice(0, 10);
    var rest = group.verses.slice(10);
    visible.forEach(function (verse) {
      section.appendChild(verseCard(verse, note));
    });

    if (rest.length) {
      var id = "g" + groupSeq++;
      pending[id] = { verses: rest, note: note };
      var more = el("button", "more", "הצג עוד " + rest.length);
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
    top.appendChild(el("span", "pair-name", pair.firstName));
    wrapper.appendChild(top);
    wrapper.appendChild(verseCard(pair.first));

    var link = el("div", "pair-link");
    link.appendChild(el("span", "pair-name", pair.secondName));
    wrapper.appendChild(link);
    wrapper.appendChild(verseCard(pair.second, pair.crossesChapter ? "מעבר פרק" : null));

    return wrapper;
  }

  function renderPairGroup(title, description, pairs) {
    if (!pairs || !pairs.length) return null;

    var section = el("section", "group");
    var head = el("div", "group-head");
    head.appendChild(el("h3", "group-title", title));
    head.appendChild(el("span", "group-count", pairs.length === 1 ? "התאמה אחת" : pairs.length + " התאמות"));
    section.appendChild(head);

    if (description) section.appendChild(el("p", "group-desc", description));
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
      var groups = [
        renderPairGroup(
          "פסוקים סמוכים",
          "פסוק אחרי פסוק: הראשון מתאים ל" + names[0] + ", והבא אחריו ל" + names[1] + ".",
          data.pairs.consecutive
        ),
        renderPairGroup(
          "פסוקים סמוכים — בסדר הפוך",
          "אותו הדבר, כאשר " + names[1] + " מופיע ראשון.",
          data.pairs.reversed
        ),
        renderPairGroup(
          "כמעט סמוכים",
          "פסוק אחד מפריד ביניהם.",
          data.pairs.nearMiss
        ),
      ];

      groups.forEach(function (group) {
        if (group) {
          results.appendChild(group);
          any = true;
        }
      });

      if (!any) {
        results.appendChild(noPairsNotice(names));
      }
    }

    data.names.forEach(function (entry) {
      var header = el("div", "name-head");
      header.appendChild(el("h2", null, entry.name));
      header.appendChild(el("span", "name-letters", entry.first + " … " + entry.last));
      results.appendChild(header);

      var groups = [
        renderGroup(
          "פסוקים לשם",
          "מתחילים באות " + entry.first + " ומסתיימים באות " + entry.last + ".",
          entry.letterMatch
        ),
        renderGroup(
          "השם מופיע בפסוק",
          "השם כמילה שלמה.",
          entry.exactWord
        ),
        renderGroup(
          "השם כחלק ממילה",
          "כולל צורות עם אותיות שימוש (ו, ה, ב, כ, ל, מ, ש) וסיומות.",
          entry.partialWord
        ),
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
          notice("לא נמצאו פסוקים עבור " + entry.name,
            "לא נמצא פסוק המתחיל באות " + entry.first + " ומסתיים באות " + entry.last + ".")
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
  function noPairsNotice(names) {
    return notice(
      "לא נמצאו פסוקים סמוכים",
      "צירוף של שני פסוקים סמוכים המתאימים ל" + names[0] + " ול" + names[1] +
      " הוא נדיר — רוב צמדי השמות אינם מופיעים כך בתנ״ך כלל. הפסוקים של כל שם בנפרד מופיעים למטה."
    );
  }

  function renderSkeleton() {
    results.innerHTML = "";
    for (var i = 0; i < 3; i++) {
      var card = el("article", "card skeleton");
      for (var j = 0; j < 4; j++) card.appendChild(el("div", "line"));
      results.appendChild(card);
    }
  }

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

    fetch("/api/search?names=" + encodeURIComponent(query), { signal: controller.signal })
      .then(function (response) {
        return response.json().then(function (body) {
          if (!response.ok) throw new Error(body.error || "החיפוש נכשל");
          return body;
        });
      })
      .then(function (data) {
        render(data);
        results.scrollIntoView({ behavior: "smooth", block: "start" });
      })
      .catch(function (error) {
        if (error.name === "AbortError") return; // superseded by a newer search
        results.innerHTML = "";
        results.appendChild(notice("שגיאה", error.message, "error"));
      })
      .then(function () {
        if (inFlight === controller) {
          inFlight = null;
          submit.disabled = false;
          results.setAttribute("aria-busy", "false");
        }
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

  fetch("/api/health")
    .then(function (r) { return r.json(); })
    .then(function (health) {
      document.getElementById("verse-count").textContent =
        health.verses.toLocaleString("he-IL") + " פסוקים, " + health.books + " ספרים.";
    })
    .catch(function () { /* the footer count is decorative */ });

  var initial = fromHash();
  if (initial) runSearch(initial, false);
})();
