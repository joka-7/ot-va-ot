/*
 * פסוק לשם — translations.
 *
 * Everything here is UI chrome: labels, buttons, headings, messages. The
 * Tanakh verse text itself is never translated -- it stays in Hebrew in every
 * locale, same as the tradition it comes from. So does the verse citation
 * (e.g. "בראשית א׳:ה׳"), which keeps its Hebrew gematria numerals regardless
 * of the UI language.
 *
 * The footer's "more about this custom" disclosure (footer.aboutHtml, set as
 * innerHTML the same way footer.attributionHtml is) is translated content,
 * unlike the verse text -- but it names specific liturgical phrases and
 * halachic sources, so the en/fr versions keep those as transliterations
 * ("Elokai Netzor", "the Shelah", "Rabbi Chaim Kanievsky") alongside the
 * translation rather than substituting a looser paraphrase. Keep the en/fr
 * entries in lockstep with the Hebrew if this text changes.
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

      "search.label": "שם לחיפוש",
      "search.placeholder": "לדוגמא: {example}",
      "search.button": "חיפוש",
      "search.hint": "שם אחד או שני/שלושה שמות, מופרדים בפסיק.",
      "search.examplesAriaLabel": "דוגמאות",
      "search.howTitle": "איך זה עובד?",
      "search.rule.noComma": "שמות בלי פסיק — אות ראשונה של השם הראשון, אות אחרונה של השם האחרון.",
      "search.rule.withComma": "שמות עם פסיק — חיפוש פסוקים עוקבים של השמות.",

      "install.button": "התקנה",
      "install.iosHint": "כדי להתקין: הקישו על כפתור השיתוף ↗ בסרגל הכלים, ואז \"הוסף למסך הבית\".",
      "install.genericHint": "כדי להתקין: פתחו את תפריט הדפדפן (⋮) ובחרו \"התקנת אפליקציה\" או \"הוספה למסך הבית\".",

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

      "pair.consecutive.title": "פסוקים סמוכים — {name1} ו{name2}",
      "pair.consecutive.desc": "פסוק אחרי פסוק: הראשון מתאים ל{name1}, והבא אחריו ל{name2}.",
      "pair.reversed.title": "פסוקים סמוכים — {name1} ו{name2} (בסדר הפוך)",
      "pair.reversed.desc": "אותו הדבר, כאשר {name2} מופיע ראשון.",
      "pair.nearMiss.title": "כמעט סמוכים — {name1} ו{name2}",
      "pair.nearMiss.desc": "פסוק אחד מפריד בין {name1} ל{name2}.",
      "pair.empty.title": "לא נמצאו פסוקים סמוכים",
      "pair.empty.desc": "צירוף של שני פסוקים סמוכים המתאימים ל{name1} ול{name2} הוא נדיר — רוב צמדי השמות אינם מופיעים כך בתנ״ך כלל. הפסוקים של כל שם בנפרד מופיעים למטה.",

      "copy.button": "העתקה",
      "copy.done": "✓ הועתק",
      "copy.toastCopied": "הפסוק הועתק",
      "copy.toastFailed": "ההעתקה נכשלה",
      "rashi.toggle": "פירוש רש״י",
      "more.button": "הצג עוד {n}",
      "group.exampleToggle": "דוגמה",
      "count.showingOf": "מציג {shown} מתוך {totalPhrase}",
      "pair.matches": { one: "התאמה אחת", other: "{n} התאמות" },
      "footer.summary": "{versesPhrase}, {booksPhrase}.",

      "error.title": "שגיאה",
      "error.generic": "החיפוש נכשל",
      "error.code.empty": "לא הוזן שם לחיפוש",
      "error.code.too_many": "אפשר לחפש בין שם אחד לשלושה שמות",
      "error.code.invalid_name": "יש להזין שם באותיות עבריות",

      "footer.attributionHtml":
        "נוסח המקרא: <strong>תנ״ך עם טעמי המקרא</strong> — מתוך " +
        "<a href=\"https://github.com/Sefaria/Sefaria-Export\" rel=\"noopener noreferrer\" target=\"_blank\">Sefaria</a>" +
        " (מקור: tanach.us), נחלת הכלל.",
      "footer.custom": "המנהג: בסוף תפילת העמידה אומרים פסוק המתחיל באות הראשונה של השם ומסתיים באות האחרונה שלו.",
      "footer.aboutTitle": "עוד על המנהג",
      "footer.aboutHtml":
        "<p>מציבים בסוף התפילה פסוק מהתנ\"ך שמתחיל באות הראשונה של שמו של המתפלל ומסתיים באות האחרונה של שמו. לחלופין, יש הנוהגים לומר פסוק שבו השם שלהם מוזכר במפורש.</p>" +
        "<p><strong>מיקום האמירה:</strong> נהוג לומר את הפסוק בסוף תפילת עמידה, בקטע של \"אלוקי נצור לשוני מרע\", מיד לפני אמירת פסוק \"יהיו לרצון אמרי פי...\" השני (הפסוק שנאמר רגע לפני שפוסעים שלושה צעדים לאחור).</p>" +
        "<p><strong>מקור המנהג:</strong> המקור הקדום ביותר מופיע כתוספת מאוחרת בפירוש רש\"י לספר מיכה (על הפסוק \"ותוּשִׁיָּה יִרְאֶה שְׁמֶךָ\"). המנהג התפרסם והתפשט מאוד בזכות השל\"ה הקדוש (רבי ישעיה הלוי הורוביץ), שהביא אותו בספרו.</p>" +
        "<p><strong>טעם המנהג:</strong> על פי תורת הסוד, כאשר אדם נפטר ומגיע לבית דין של מעלה, מלאכי הדין שואלים אותו מה שמו. מרוב הבהלה והפחד של יום הדין, הרשעים שוכחים את שמם. האמירה היומיומית של הפסוק הקשור לשם האדם בתפילה, מהווה סגולה לכך שהאדם לא ישכח את שמו ליום הדין.</p>" +
        "<p><strong>שני שמות או יותר:</strong> מי שיש לו שני שמות, נהגו רבים לומר פסוק נפרד לכל אחד מהשמות. מנהג נוסף (כפי שהורה הרב חיים קנייבסקי) הוא לומר בנוסף פסוק המתחיל באות הראשונה של השם הראשון ומסתיים באות האחרונה של השם השני.</p>",
      "footer.credit": "נבנה על ידי",
      "footer.verses": { one: "פסוק אחד", two: "שני פסוקים", other: "{n} פסוקים" },
      "footer.books": { one: "ספר אחד", two: "שני ספרים", other: "{n} ספרים" },
    },

    en: {
      "meta.description": "Find a Tanakh verse matching a name's first and last letter, per the Jewish custom of saying a verse for one's name at the end of the Amidah.",
      "doc.title": "A Verse for the Name — Search the Tanakh by Name",

      "header.title": "A Verse for the Name",
      "header.subtitle": "Find Tanakh verses that begin and end with the letters of the name/names",

      "search.label": "Name to search",
      "search.placeholder": "e.g. {example}",
      "search.button": "Search",
      "search.hint": "One name, or two/three names, separated by a comma.",
      "search.examplesAriaLabel": "Examples",
      "search.howTitle": "How does this work?",
      "search.rule.noComma": "Names without a comma — the first letter of the first name, the last letter of the last name.",
      "search.rule.withComma": "Names with a comma — search for consecutive verses of the names.",

      "install.button": "Install",
      "install.iosHint": "To install: tap the Share button ↗ in the toolbar, then \"Add to Home Screen\".",
      "install.genericHint": "To install: open your browser's menu (⋮) and choose \"Install app\" or \"Add to Home Screen\".",

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

      "pair.consecutive.title": "Consecutive Verses — {name1} and {name2}",
      "pair.consecutive.desc": "Verse after verse: the first matches {name1}, and the one right after it matches {name2}.",
      "pair.reversed.title": "Consecutive Verses — {name1} and {name2} (Reversed)",
      "pair.reversed.desc": "The same, with {name2} appearing first.",
      "pair.nearMiss.title": "Near-Consecutive — {name1} and {name2}",
      "pair.nearMiss.desc": "One verse separates {name1} and {name2}.",
      "pair.empty.title": "No consecutive verses found",
      "pair.empty.desc": "A pair of consecutive verses matching {name1} and {name2} is rare — most name pairs don't occur that way in the Tanakh at all. Each name's own verses appear below.",

      "copy.button": "Copy",
      "copy.done": "✓ Copied",
      "copy.toastCopied": "Verse copied",
      "copy.toastFailed": "Copy failed",
      "rashi.toggle": "Rashi's Commentary",
      "more.button": "Show {n} more",
      "group.exampleToggle": "Example",
      "count.showingOf": "Showing {shown} of {totalPhrase}",
      "pair.matches": { one: "1 match", other: "{n} matches" },
      "footer.summary": "{versesPhrase}, {booksPhrase}.",

      "error.title": "Error",
      "error.generic": "Search failed",
      "error.code.empty": "Enter a name to search",
      "error.code.too_many": "You can search for one, two, or three names, no more",
      "error.code.invalid_name": "Enter a name using Hebrew letters",

      "footer.attributionHtml":
        "Biblical text: <strong>Tanach with Ta'amei Hamikra</strong> — from " +
        "<a href=\"https://github.com/Sefaria/Sefaria-Export\" rel=\"noopener noreferrer\" target=\"_blank\">Sefaria</a>" +
        " (source: tanach.us), Public Domain.",
      "footer.custom": "The custom: at the end of the Amidah, one recites a verse that begins with the first letter of one's name and ends with its last letter.",
      "footer.aboutTitle": "More about this custom",
      "footer.aboutHtml":
        "<p>At the end of the prayer, one places a verse from the Tanakh that begins with the first letter of the worshipper's name and ends with the last letter of their name. Alternatively, some have the custom of saying a verse in which their name is mentioned explicitly.</p>" +
        "<p><strong>Where it's said:</strong> It is customary to say the verse at the end of the Amidah, in the passage of \"Elokai Netzor Leshoni Mera\" (\"My God, guard my tongue from evil\"), immediately before the second recitation of \"Yihyu Leratzon Imrei Fi...\" (\"May the words of my mouth be pleasing...\") — the verse said just before taking three steps back.</p>" +
        "<p><strong>Source of the custom:</strong> The earliest source appears as a later addition to Rashi's commentary on the book of Micah (on the verse \"U'tushiyah Yireh Shemecha\"). The custom became widely known mainly thanks to the holy Shelah (Rabbi Yeshayahu HaLevi Horowitz), who brought it in his book.</p>" +
        "<p><strong>Reason for the custom:</strong> According to Kabbalistic teaching, when a person passes away and reaches the heavenly court, the angels of judgment ask for their name. In the panic and fear of the Day of Judgment, the wicked forget their own name. Saying the verse tied to one's name daily in prayer is a segulah (a spiritual remedy) so that the person will not forget their name on the Day of Judgment.</p>" +
        "<p><strong>Two names or more:</strong> Someone with two names customarily says a separate verse for each name. Another custom (as instructed by Rabbi Chaim Kanievsky) is to also say a verse that begins with the first letter of the first name and ends with the last letter of the second name.</p>",
      "footer.credit": "Built by",
      "footer.verses": { one: "1 verse", other: "{n} verses" },
      "footer.books": { one: "1 book", other: "{n} books" },
    },

    fr: {
      "meta.description": "Trouver un verset du Tanakh dont la première et la dernière lettre correspondent à celles d'un prénom, selon la coutume juive de réciter un verset pour son prénom à la fin de l'Amida.",
      "doc.title": "Un verset pour le prénom — Recherche dans le Tanakh",

      "header.title": "Un verset pour le prénom",
      "header.subtitle": "Trouver les versets du Tanakh qui commencent et finissent par les lettres du prénom/des prénoms",

      "search.label": "Prénom à rechercher",
      "search.placeholder": "par ex. {example}",
      "search.button": "Rechercher",
      "search.hint": "Un prénom, ou deux/trois prénoms, séparés par une virgule.",
      "search.examplesAriaLabel": "Exemples",
      "search.howTitle": "Comment ça marche ?",
      "search.rule.noComma": "Prénoms sans virgule — première lettre du premier prénom, dernière lettre du dernier prénom.",
      "search.rule.withComma": "Prénoms avec une virgule — recherche de versets consécutifs des prénoms.",

      "install.button": "Installer",
      "install.iosHint": "Pour installer : appuyez sur le bouton Partager ↗ dans la barre d'outils, puis « Sur l'écran d'accueil ».",
      "install.genericHint": "Pour installer : ouvrez le menu du navigateur (⋮) et choisissez « Installer l'application » ou « Ajouter à l'écran d'accueil ».",

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

      "pair.consecutive.title": "Versets consécutifs — {name1} et {name2}",
      "pair.consecutive.desc": "Verset après verset : le premier correspond à {name1}, et celui qui suit correspond à {name2}.",
      "pair.reversed.title": "Versets consécutifs — {name1} et {name2} (ordre inversé)",
      "pair.reversed.desc": "La même chose, {name2} apparaissant en premier.",
      "pair.nearMiss.title": "Presque consécutifs — {name1} et {name2}",
      "pair.nearMiss.desc": "Un verset sépare {name1} et {name2}.",
      "pair.empty.title": "Aucun verset consécutif trouvé",
      "pair.empty.desc": "Une paire de versets consécutifs correspondant à {name1} et {name2} est rare — la plupart des paires de prénoms n'apparaissent pas ainsi dans le Tanakh. Les versets propres à chaque prénom apparaissent ci-dessous.",

      "copy.button": "Copier",
      "copy.done": "✓ Copié",
      "copy.toastCopied": "Verset copié",
      "copy.toastFailed": "Échec de la copie",
      "rashi.toggle": "Commentaire de Rashi",
      "more.button": "Afficher {n} de plus",
      "group.exampleToggle": "Exemple",
      "count.showingOf": "Affichage de {shown} sur {totalPhrase}",
      "pair.matches": { one: "1 correspondance", other: "{n} correspondances" },
      "footer.summary": "{versesPhrase}, {booksPhrase}.",

      "error.title": "Erreur",
      "error.generic": "La recherche a échoué",
      "error.code.empty": "Saisissez un prénom à rechercher",
      "error.code.too_many": "Vous pouvez rechercher un, deux ou trois prénoms, pas plus",
      "error.code.invalid_name": "Saisissez un prénom en lettres hébraïques",

      "footer.attributionHtml":
        "Texte biblique : <strong>Tanach avec Ta'amei Hamikra</strong> — provenant de " +
        "<a href=\"https://github.com/Sefaria/Sefaria-Export\" rel=\"noopener noreferrer\" target=\"_blank\">Sefaria</a>" +
        " (source : tanach.us), domaine public.",
      "footer.custom": "La coutume : à la fin de l'Amida, on récite un verset qui commence par la première lettre de son prénom et finit par sa dernière lettre.",
      "footer.aboutTitle": "En savoir plus sur cette coutume",
      "footer.aboutHtml":
        "<p>On place à la fin de la prière un verset du Tanakh qui commence par la première lettre du prénom de celui qui prie et se termine par la dernière lettre de son prénom. Autrement, certains ont l'usage de réciter un verset où leur prénom est mentionné explicitement.</p>" +
        "<p><strong>Où on le récite :</strong> il est d'usage de réciter ce verset à la fin de l'Amida, dans le passage de « Elokaï Netsor Lechoni Méra » (« Mon Dieu, garde ma langue du mal »), juste avant la seconde récitation du verset « Yihyou Leratsone Imré Phi... » (« Que les paroles de ma bouche soient agréables... »), le verset dit juste avant de reculer de trois pas.</p>" +
        "<p><strong>Origine de la coutume :</strong> la source la plus ancienne apparaît comme un ajout tardif au commentaire de Rachi sur le livre de Michée (sur le verset « Outouchiya Yiré Chémécha »). La coutume s'est répandue surtout grâce au saint Chela (Rabbi Yeshaya HaLévi Horowitz), qui l'a rapportée dans son livre.</p>" +
        "<p><strong>Raison de la coutume :</strong> selon l'enseignement kabbalistique, lorsqu'une personne décède et se présente devant le tribunal céleste, les anges du jugement lui demandent son nom. Dans la panique et la peur du jour du Jugement, les impies oublient leur propre nom. Réciter chaque jour, dans la prière, le verset lié à son prénom, constitue une segoula (un moyen spirituel) pour ne pas oublier son nom au jour du Jugement.</p>" +
        "<p><strong>Deux prénoms ou plus :</strong> celui qui porte deux prénoms a, selon un usage répandu, l'habitude de réciter un verset séparé pour chacun des deux prénoms. Un autre usage (tel qu'enseigné par le Rav Chaïm Kanievsky) consiste à réciter en plus un verset qui commence par la première lettre du premier prénom et se termine par la dernière lettre du second prénom.</p>",
      "footer.credit": "Créé par",
      "footer.verses": { one: "1 verset", other: "{n} versets" },
      "footer.books": { one: "1 livre", other: "{n} livres" },
    },
  };

  // A fixed, always-Hebrew example shown inside the search placeholder in
  // every locale -- the field itself only ever accepts Hebrew names.
  var PLACEHOLDER_EXAMPLE = "אברהם, יצחק או שרה, רבקה";

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

  /*
   * Per-result-group worked examples, revealed on demand ("show example")
   * under that group's description. A group with no entry here simply gets
   * no toggle at all -- nothing to see until content is added. Keys match the
   * `exampleKey` passed to renderGroup/renderPairGroup in app.js:
   * group.letterMatch, group.exactWord, group.partialWord, pair.consecutive,
   * pair.reversed, pair.nearMiss. Add the Hebrew text first; keep English and
   * French entries in lockstep with any Hebrew addition.
   */
  var EXAMPLES = {
    // "group.letterMatch": { he: "...", en: "...", fr: "..." },
  };

  function example(locale, key) {
    var entry = EXAMPLES[key];
    if (!entry) return null;
    return entry[locale] || entry[DEFAULT_LOCALE] || null;
  }

  return {
    LOCALES: LOCALES,
    DEFAULT_LOCALE: DEFAULT_LOCALE,
    PLACEHOLDER_EXAMPLE: PLACEHOLDER_EXAMPLE,
    isSupported: isSupported,
    t: t,
    plural: plural,
    formatNumber: formatNumber,
    example: example,
  };
})();
