/* Frontend statique, sans dépendance. Lit data/briefings/*.json (générés par le pipeline
   Python) et les affiche. Aucune donnée n'est inventée côté client : si un champ est absent
   ou null, la section correspondante est simplement omise ou signalée. */

const DATA_BASE = "data/briefings"; // docs/data/briefings, servi par GitHub Pages avec le reste de docs/

function el(tag, opts = {}, children = []) {
  const node = document.createElement(tag);
  if (opts.class) node.className = opts.class;
  if (opts.text) node.textContent = opts.text;
  if (opts.html) node.innerHTML = opts.html;
  for (const child of children) if (child) node.appendChild(child);
  return node;
}

function formatDateFr(dateIso) {
  try {
    const d = new Date(dateIso + "T00:00:00");
    return d.toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  } catch {
    return dateIso;
  }
}

function formatHeureFr(isoString) {
  try {
    const d = new Date(isoString);
    return d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "—";
  }
}

/* Rendu markdown minimal : titres "## " -> h3, paragraphes séparés par ligne vide.
   Volontairement simple (pas de dépendance externe), suffisant pour le contenu généré
   par le prompt qui produit du texte structuré simple. */
function renderMarkdown(md) {
  if (!md) return el("p", { text: "" });
  const container = el("div");
  const blocks = md.split(/\n\s*\n/);
  for (const block of blocks) {
    const trimmed = block.trim();
    if (!trimmed) continue;
    if (trimmed.startsWith("## ")) {
      container.appendChild(el("h3", { text: trimmed.slice(3).trim() }));
    } else if (trimmed.startsWith("# ")) {
      container.appendChild(el("h3", { text: trimmed.slice(2).trim() }));
    } else {
      container.appendChild(el("p", { text: trimmed.replace(/\n/g, " ") }));
    }
  }
  return container;
}

function renderArticle(item) {
  const meta = el("div", { class: "article__meta" });
  if (item.statut) {
    const tag = el("span", {
      class: "tag " + (item.statut === "fait_confirme" ? "tag--confirme" : "tag--rapporte"),
      text: item.statut === "fait_confirme" ? "Fait confirmé" : "Information rapportée",
    });
    meta.appendChild(tag);
  }
  if (item.sources && item.sources.length) {
    meta.appendChild(el("span", { text: item.sources.join(" · ") }));
  }

  const children = [el("h4", { class: "article__title", text: item.titre })];
  if (item.resume) children.push(el("p", { class: "article__body", text: item.resume }));
  if (item.pourquoi_important) {
    children.push(el("p", { class: "article__why", html: `<strong>Pourquoi c'est important.</strong> ${escapeHtml(item.pourquoi_important)}` }));
  }
  if (item.consequences) {
    children.push(el("p", { class: "article__why", html: `<strong>Conséquences possibles.</strong> ${escapeHtml(item.consequences)}` }));
  }
  children.push(meta);

  return el("div", { class: "article" }, children);
}

function escapeHtml(str) {
  const d = document.createElement("div");
  d.textContent = str;
  return d.innerHTML;
}

function renderSectionActualite(actualite) {
  const section = el("section", { class: "section" }, [el("h2", { class: "section-title", text: "Actualité" })]);
  if (!actualite) {
    section.appendChild(el("p", { class: "loading", text: "Aucune actualité disponible pour ce briefing." }));
    return section;
  }
  if (actualite.france && actualite.france.length) {
    section.appendChild(el("h3", { class: "subsection-title", text: "France" }));
    for (const item of actualite.france) section.appendChild(renderArticle(item));
  }
  if (actualite.monde && actualite.monde.length) {
    section.appendChild(el("h3", { class: "subsection-title", text: "Monde" }));
    for (const item of actualite.monde) section.appendChild(renderArticle(item));
  }
  if (!(actualite.france || []).length && !(actualite.monde || []).length) {
    section.appendChild(el("p", { class: "loading", text: "Aucune actualité jugée suffisamment importante ce jour." }));
  }
  return section;
}

function renderSectionMarches(marches) {
  const section = el("section", { class: "section" }, [el("h2", { class: "section-title", text: "Marchés" })]);
  if (!marches) {
    section.appendChild(el("p", { class: "loading", text: "Données de marché indisponibles." }));
    return section;
  }
  if (marches.resume_court) section.appendChild(el("p", { class: "market-summary", text: marches.resume_court }));

  const notables = marches.mouvements_notables || [];
  if (notables.length) {
    const list = el("div", { class: "market-list" });
    for (const m of notables) {
      const sign = m.variation_pct > 0 ? "up" : m.variation_pct < 0 ? "down" : "";
      const valueText = m.variation_pct != null ? `${m.variation_pct > 0 ? "+" : ""}${m.variation_pct}%` : "—";
      const row = el("div", { class: "market-item" }, [
        el("span", { class: "market-item__name", text: m.nom }),
        el("span", { class: `market-item__value ${sign}`, text: valueText }),
      ]);
      if (m.explication) row.appendChild(el("span", { class: "market-item__explication", text: m.explication }));
      list.appendChild(row);
    }
    section.appendChild(list);
  } else {
    section.appendChild(el("p", { class: "loading", text: "Aucun mouvement de marché notable aujourd'hui." }));
  }
  return section;
}

function renderSectionSport(sport) {
  const section = el("section", { class: "section" }, [el("h2", { class: "section-title", text: "Sport" })]);
  if (!sport) return section;

  const labels = { football: "Football", basketball: "Basketball", natation: "Natation", autres: "Autres sports" };
  let any = false;
  for (const key of ["football", "basketball", "natation", "autres"]) {
    const items = sport[key];
    if (items && items.length) {
      any = true;
      section.appendChild(el("h3", { class: "subsection-title", text: labels[key] }));
      const list = el("ul", { class: "sport-list" });
      for (const line of items) list.appendChild(el("li", { text: line }));
      section.appendChild(list);
    }
  }
  if (!any) section.appendChild(el("p", { class: "loading", text: "Rien de notable aujourd'hui." }));
  return section;
}

function renderSectionScience(science) {
  const section = el("section", { class: "section" }, [el("h2", { class: "section-title", text: "Science & technologie" })]);
  if (!science) {
    section.appendChild(el("p", { class: "loading", text: "Sujet scientifique indisponible." }));
    return section;
  }
  section.appendChild(el("h3", { class: "subsection-title", text: science.titre }));
  section.appendChild(el("div", { class: "science-article" }, [renderMarkdown(science.contenu_markdown)]));
  return section;
}

function renderSectionMeteo(meteo) {
  const section = el("section", { class: "section" }, [el("h2", { class: "section-title", text: "Météo — Antibes, Cannes, Valbonne, Grasse" })]);
  if (!meteo) {
    section.appendChild(el("p", { class: "loading", text: "Météo indisponible." }));
    return section;
  }
  const strip = el("div", { class: "weather-strip" }, [
    el("span", { class: "weather-strip__temp", text: meteo.temperature_max_zone != null ? `${Math.round(meteo.temperature_max_zone)}°` : "—" }),
    el("span", { class: "weather-strip__desc", text: meteo.description_dominante || "" }),
  ]);
  if (meteo.probabilite_pluie_max_pct != null) {
    strip.appendChild(el("span", { class: "weather-strip__desc", text: `Pluie: ${meteo.probabilite_pluie_max_pct}%` }));
  }
  if (meteo.vent_max_kmh != null) {
    strip.appendChild(el("span", { class: "weather-strip__desc", text: `Vent: ${Math.round(meteo.vent_max_kmh)} km/h` }));
  }
  section.appendChild(strip);

  if (meteo.villes_detail && meteo.villes_detail.length) {
    const detail = meteo.villes_detail.map((v) => `${v.ville}: ${v.temperature_actuelle != null ? Math.round(v.temperature_actuelle) + "°" : "—"}`).join(" · ");
    section.appendChild(el("p", { class: "weather-cities", text: detail }));
  }
  return section;
}

function renderSectionCitation(citation) {
  if (!citation || !citation.texte) return null;
  const section = el("section", { class: "section" }, [el("h2", { class: "section-title", text: "Citation du jour" })]);
  section.appendChild(
    el("div", { class: "quote" }, [
      el("span", { class: "quote__mark", text: "“" }),
      el("p", { class: "quote__text", text: citation.texte }),
      el("p", { class: "quote__author", text: citation.auteur }),
    ])
  );
  return section;
}

async function loadJson(path) {
  const resp = await fetch(path, { cache: "no-store" });
  if (!resp.ok) throw new Error(`HTTP ${resp.status} sur ${path}`);
  return resp.json();
}

async function renderIndexPage() {
  const content = document.getElementById("content");
  const params = new URLSearchParams(window.location.search);
  const requestedDate = params.get("date");
  const targetFile = requestedDate ? `${DATA_BASE}/${requestedDate}.json` : `${DATA_BASE}/latest.json`;

  try {
    const [enveloppe, status] = await Promise.allSettled([
      loadJson(targetFile),
      loadJson(`${DATA_BASE}/status.json`),
    ]);

    if (enveloppe.status !== "fulfilled") {
      content.innerHTML = "";
      content.appendChild(el("p", { text: "Aucun briefing disponible pour le moment. Revenez après la première génération automatique." }));
      return;
    }

    const { date, derniere_mise_a_jour, briefing } = enveloppe.value;
    document.getElementById("date-briefing").textContent = formatDateFr(date);
    document.getElementById("derniere-maj").textContent = `mise à jour ${formatHeureFr(derniere_mise_a_jour)}`;

    if (!requestedDate && status.status === "fulfilled" && status.value && status.value.succes === false) {
      const banner = document.getElementById("status-banner");
      banner.hidden = false;
      banner.textContent = "La dernière tentative de mise à jour a échoué. Vous consultez le dernier briefing valide.";
    }

    content.innerHTML = "";
    content.appendChild(renderSectionActualite(briefing.actualite));
    content.appendChild(renderSectionMarches(briefing.marches));
    content.appendChild(renderSectionSport(briefing.sport));
    content.appendChild(renderSectionScience(briefing.science));
    content.appendChild(renderSectionMeteo(briefing.meteo));
    const quoteSection = renderSectionCitation(briefing.citation);
    if (quoteSection) content.appendChild(quoteSection);
  } catch (err) {
    content.innerHTML = "";
    content.appendChild(el("p", { text: "Erreur de chargement du briefing. Réessayez plus tard." }));
    console.error(err);
  }
}

async function renderHistoryPage() {
  const list = document.getElementById("history-list");
  try {
    const index = await loadJson(`${DATA_BASE}/index.json`);
    list.innerHTML = "";
    if (!index.dates || !index.dates.length) {
      list.appendChild(el("li", { text: "Aucun briefing archivé pour le moment." }));
      return;
    }
    for (const dateIso of index.dates) {
      const li = el("li", {}, [el("a", { text: formatDateFr(dateIso) })]);
      li.querySelector("a").href = `briefing.html?date=${dateIso}`;
      list.appendChild(li);
    }
  } catch (err) {
    list.innerHTML = "";
    list.appendChild(el("li", { text: "Impossible de charger l'historique." }));
    console.error(err);
  }
}

if (document.getElementById("content") && document.getElementById("date-briefing")) {
  renderIndexPage();
} else if (document.getElementById("history-list")) {
  renderHistoryPage();
}
