/*
 * פסוק לשם — translations.
 *
 * Everything here is UI chrome: labels, buttons, headings, messages. The
 * Tanakh verse text itself is never translated -- it stays in Hebrew in every
 * locale, same as the tradition it comes from. So does the verse citation
 * (e.g. "בראשית א׳:ה׳"), which keeps its Hebrew gematria numerals regardless
 * of the UI language.
 *
 * Loaded before app.js, which owns the interpolation and DOM wiring; this
 * file only holds data and locale-formatting helpers.
 */

var I18N = (function () {
  "use strict";

  var STRINGS = {
    he: {
      "meta.description": "חיפוש פסוק בתנ״ך לפי האות הראשונה והאחרונה של השם, לפי המנהג לומר פסוק לשם בסוף תפילת העמידה.",
      "doc.title": "פסוק לשם — חיפוש פסוקים בתנ״ך לפי שם",

      "header.title": "פסוק לשם",
      "header.subtitle": "מציאת פסוקים בתנ״ך המתחילים ומסתיימים באותיות השם/שמות",

      "search.label": "שם, או שני שמות מופרדים בפסיק",
      "search.placeholder": "לדוגמה: {example}",
      "search.button": "חיפוש",
      "search.hint": "שם אחד — פסוקים לשם. שני שמות — גם פסוקים סמוכים לזוג.",
      "search.examplesAriaLabel": "דוגמאות",

      "waking.message": "מעיר את השרת… בפעם הראשונה אחרי זמן מנוחה זה עלול לקחת כדקה.",

      "badge.chapter": "פרק {n}",
      "badge.verse": "פסוק {n}",
      "badge.crossesChapter": "מעבר פרק",

      "group.letterMatch.title": "פסוקים לשם",
      "group.letterMatch.desc": "מתחילים באות {first} ומסתיימים באות {last}.",
      "group.exactWord.title": "השם מופיע בפסוק",
      "group.exactWord.desc": "השם כמילה שלמה.",
      "group.partialWord.title": "השם כחלק ממילה",
      "group.partialWord.desc": "כולל צורות עם אותיות שימוש (ו, ה, ב, כ, ל, מ, ש) וסיומות.",
      "group.empty.title": "לא נמצאו פסוקים עבור {name}",
      "group.empty.desc": "לא נמצא פסוק המתחיל באות {first} ומסתיים באות {last}.",

      "pair.consecutive.title": "פסוקים סמוכים",
      "pair.consecutive.desc": "פסוק אחרי פסוק: הראשון מתאים ל{name1}, והבא אחריו ל{name2}.",
      "pair.reversed.title": "פסוקים סמוכים — בסדר הפוך",
      "pair.reversed.desc": "אותו הדבר, כאשר {name2} מופיע ראשון.",
      "pair.nearMiss.title": "כמעט סמוכים",
      "pair.nearMiss.desc": "פסוק אחד מפריד ביניהם.",
      "pair.empty.title": "לא נמצאו פסוקים סמוכים",
      "pair.empty.desc": "צירוף של שני פסוקים סמוכים המתאימים ל{name1} ול{name2} הוא נדיר — רוב צמדי השמות אינם מופיעים כך בתנ״ך כלל. הפסוקים של כל שם בנפרד מופיעים למטה.",

      "copy.button": "העתקה",
      "copy.done": "✓ הועתק",
      "copy.toastCopied": "הפסוק הועתק",
      "copy.toastFailed": "ההעתקה נכשלה",
      "more.button": "הצג עוד {n}",
      "count.showingOf": "מציג {shown} מתוך {totalPhrase}",
      "pair.matches": { one: "התאמה אחת", other: "{n} התאמות" },
      "footer.summary": "{versesPhrase}, {booksPhrase}.",

      "error.title": "שגיאה",
      "error.generic": "החיפוש נכשל",
      "error.code.empty": "לא הוזן שם לחיפוש",
      "error.code.too_many": "אפשר לחפש שם אחד או שני שמות בלבד",
      "error.code.invalid_name": "יש להזין שם באותיות עבריות",

      "footer.attributionHtml":
        "נוסח המקרא: <strong>תנ״ך עם טעמי המקרא</strong> — מתוך " +
        "<a href=\"https://github.com/Sefaria/Sefaria-Export\" rel=\"noopener noreferrer\" target=\"_blank\">Sefaria</a>" +
        " (מקור: tanach.us), נחלת הכלל.",
      "footer.custom": "המנהג: בסוף תפילת העמידה אומרים פסוק המתחיל באות הראשונה של השם ומסתיים באות האחרונה שלו.",
      "footer.credit": "נבנה על ידי",
      "footer.verses": { one: "פסוק אחד", two: "שני פסוקים", other: "{n} פסוקים" },
      "footer.books": { one: "ספר אחד", two: "שני ספרים", other: "{n} ספרים" },
    },

    en: {
      "meta.description": "Find a Tanakh verse matching a name's first and last letter, per the Jewish custom of saying a verse for one's name at the end of the Amidah.",
      "doc.title": "A Verse for the Name — Search the Tanakh by Name",

      "header.title": "A Verse for the Name",
      "header.subtitle": "Find Tanakh verses that begin and end with the letters of the name/names",

      "search.label": "A name, or two names separated by a comma",
      "search.placeholder": "e.g. {example}",
      "search.button": "Search",
      "search.hint": "One name — verses for it. Two names — also consecutive verses for the pair.",
      "search.examplesAriaLabel": "Examples",

      "waking.message": "Waking up the server… the first request after a while can take up to a minute.",

      "badge.chapter": "Chapter {n}",
      "badge.verse": "Verse {n}",
      "badge.crossesChapter": "Crosses a chapter",

      "group.letterMatch.title": "Verses for the Name",
      "group.letterMatch.desc": "Begin with the letter {first} and end with the letter {last}.",
      "group.exactWord.title": "The Name Appears in the Verse",
      "group.exactWord.desc": "The name as a whole word.",
      "group.partialWord.title": "The Name as Part of a Word",
      "group.partialWord.desc": "Includes forms with attached prefixes (ו, ה, ב, כ, ל, מ, ש) and suffixes.",
      "group.empty.title": "No verses found for {name}",
      "group.empty.desc": "No verse begins with the letter {first} and ends with the letter {last}.",

      "pair.consecutive.title": "Consecutive Verses",
      "pair.consecutive.desc": "Verse after verse: the first matches {name1}, and the one right after it matches {name2}.",
      "pair.reversed.title": "Consecutive Verses — Reversed Order",
      "pair.reversed.desc": "The same, with {name2} appearing first.",
      "pair.nearMiss.title": "Near-Consecutive",
      "pair.nearMiss.desc": "One verse separates them.",
      "pair.empty.title": "No consecutive verses found",
      "pair.empty.desc": "A pair of consecutive verses matching {name1} and {name2} is rare — most name pairs don't occur that way in the Tanakh at all. Each name's own verses appear below.",

      "copy.button": "Copy",
      "copy.done": "✓ Copied",
      "copy.toastCopied": "Verse copied",
      "copy.toastFailed": "Copy failed",
      "more.button": "Show {n} more",
      "count.showingOf": "Showing {shown} of {totalPhrase}",
      "pair.matches": { one: "1 match", other: "{n} matches" },
      "footer.summary": "{versesPhrase}, {booksPhrase}.",

      "error.title": "Error",
      "error.generic": "Search failed",
      "error.code.empty": "Enter a name to search",
      "error.code.too_many": "You can search for one name or two, no more",
      "error.code.invalid_name": "Enter a name using Hebrew letters",

      "footer.attributionHtml":
        "Biblical text: <strong>Tanach with Ta'amei Hamikra</strong> — from " +
        "<a href=\"https://github.com/Sefaria/Sefaria-Export\" rel=\"noopener noreferrer\" target=\"_blank\">Sefaria</a>" +
        " (source: tanach.us), Public Domain.",
      "footer.custom": "The custom: at the end of the Amidah, one recites a verse that begins with the first letter of one's name and ends with its last letter.",
      "footer.credit": "Built by",
      "footer.verses": { one: "1 verse", other: "{n} verses" },
      "footer.books": { one: "1 book", other: "{n} books" },
    },

    fr: {
      "meta.description": "Trouver un verset du Tanakh dont la première et la dernière lettre correspondent à celles d'un prénom, selon la coutume juive de réciter un verset pour son prénom à la fin de l'Amida.",
      "doc.title": "Un verset pour le prénom — Recherche dans le Tanakh",

      "header.title": "Un verset pour le prénom",
      "header.subtitle": "Trouver les versets du Tanakh qui commencent et finissent par les lettres du prénom/des prénoms",

      "search.label": "Un prénom, ou deux prénoms séparés par une virgule",
      "search.placeholder": "par ex. {example}",
      "search.button": "Rechercher",
      "search.hint": "Un prénom — les versets qui lui correspondent. Deux prénoms — aussi les versets consécutifs du couple.",
      "search.examplesAriaLabel": "Exemples",

      "waking.message": "Réveil du serveur… la première requête après une pause peut prendre jusqu'à une minute.",

      "badge.chapter": "Chapitre {n}",
      "badge.verse": "Verset {n}",
      "badge.crossesChapter": "Change de chapitre",

      "group.letterMatch.title": "Versets pour le prénom",
      "group.letterMatch.desc": "Commencent par la lettre {first} et finissent par la lettre {last}.",
      "group.exactWord.title": "Le prénom apparaît dans le verset",
      "group.exactWord.desc": "Le prénom en tant que mot entier.",
      "group.partialWord.title": "Le prénom au sein d'un mot",
      "group.partialWord.desc": "Inclut les formes avec préfixes attachés (ו, ה, ב, כ, ל, מ, ש) et suffixes.",
      "group.empty.title": "Aucun verset trouvé pour {name}",
      "group.empty.desc": "Aucun verset ne commence par la lettre {first} et ne finit par la lettre {last}.",

      "pair.consecutive.title": "Versets consécutifs",
      "pair.consecutive.desc": "Verset après verset : le premier correspond à {name1}, et celui qui suit correspond à {name2}.",
      "pair.reversed.title": "Versets consécutifs — ordre inversé",
      "pair.reversed.desc": "La même chose, {name2} apparaissant en premier.",
      "pair.nearMiss.title": "Presque consécutifs",
      "pair.nearMiss.desc": "Un verset les sépare.",
      "pair.empty.title": "Aucun verset consécutif trouvé",
      "pair.empty.desc": "Une paire de versets consécutifs correspondant à {name1} et {name2} est rare — la plupart des paires de prénoms n'apparaissent pas ainsi dans le Tanakh. Les versets propres à chaque prénom apparaissent ci-dessous.",

      "copy.button": "Copier",
      "copy.done": "✓ Copié",
      "copy.toastCopied": "Verset copié",
      "copy.toastFailed": "Échec de la copie",
      "more.button": "Afficher {n} de plus",
      "count.showingOf": "Affichage de {shown} sur {totalPhrase}",
      "pair.matches": { one: "1 correspondance", other: "{n} correspondances" },
      "footer.summary": "{versesPhrase}, {booksPhrase}.",

      "error.title": "Erreur",
      "error.generic": "La recherche a échoué",
      "error.code.empty": "Saisissez un prénom à rechercher",
      "error.code.too_many": "Vous pouvez rechercher un ou deux prénoms, pas plus",
      "error.code.invalid_name": "Saisissez un prénom en lettres hébraïques",

      "footer.attributionHtml":
        "Texte biblique : <strong>Tanach avec Ta'amei Hamikra</strong> — provenant de " +
        "<a href=\"https://github.com/Sefaria/Sefaria-Export\" rel=\"noopener noreferrer\" target=\"_blank\">Sefaria</a>" +
        " (source : tanach.us), domaine public.",
      "footer.custom": "La coutume : à la fin de l'Amida, on récite un verset qui commence par la première lettre de son prénom et finit par sa dernière lettre.",
      "footer.credit": "Créé par",
      "footer.verses": { one: "1 verset", other: "{n} versets" },
      "footer.books": { one: "1 livre", other: "{n} livres" },
    },
  };

  // A fixed, always-Hebrew example shown inside the search placeholder in
  // every locale -- the field itself only ever accepts Hebrew names.
  var PLACEHOLDER_EXAMPLE = "אברהם, שרה";

  var LOCALES = ["he", "en", "fr"];
  var DEFAULT_LOCALE = "he";

  // Locale used for Intl.NumberFormat-style grouping (footer counts, "showing
  // X of Y"). Hebrew UI keeps Hebrew-Indic grouping via he-IL.
  var NUMBER_LOCALE = { he: "he-IL", en: "en-US", fr: "fr-FR" };

  function isSupported(locale) {
    return LOCALES.indexOf(locale) !== -1;
  }

  /* Fill {token} placeholders in a template string from a vars object. */
  function interpolate(template, vars) {
    if (!vars) return template;
    return template.replace(/\{(\w+)\}/g, function (match, key) {
      return Object.prototype.hasOwnProperty.call(vars, key) ? vars[key] : match;
    });
  }

  /*
   * t(locale, key, vars) — plain string lookup with interpolation.
   * Falls back to Hebrew, then to the key itself, so a missing translation
   * never renders as literal "undefined" in the UI.
   */
  function t(locale, key, vars) {
    var table = STRINGS[locale] || STRINGS[DEFAULT_LOCALE];
    var template = table[key];
    if (template == null) template = STRINGS[DEFAULT_LOCALE][key];
    if (template == null) return key;
    if (typeof template !== "string") return key; // a plural table, not a plain string
    return interpolate(template, vars);
  }

  /*
   * plural(locale, key, n) — picks "one"/"two"/"other" from a plural table
   * and interpolates {n} with locale-appropriate digit grouping. Hebrew has a
   * dedicated dual form (two names use "שני X" rather than "2 X"); English and
   * French only distinguish one/other.
   */
  function plural(locale, key, n) {
    var table = (STRINGS[locale] || STRINGS[DEFAULT_LOCALE])[key];
    if (!table) return String(n);
    var form = n === 1 ? "one" : (n === 2 && table.two) ? "two" : "other";
    var template = table[form] || table.other;
    return interpolate(template, { n: formatNumber(locale, n) });
  }

  function formatNumber(locale, n) {
    try {
      return n.toLocaleString(NUMBER_LOCALE[locale] || NUMBER_LOCALE[DEFAULT_LOCALE]);
    } catch (err) {
      return String(n);
    }
  }

  return {
    LOCALES: LOCALES,
    DEFAULT_LOCALE: DEFAULT_LOCALE,
    PLACEHOLDER_EXAMPLE: PLACEHOLDER_EXAMPLE,
    isSupported: isSupported,
    t: t,
    plural: plural,
    formatNumber: formatNumber,
  };
})();
