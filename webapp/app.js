const PAGE_SIZE = 12;

const state = {
  books: [],
  filtered: [],
  genres: [],
  page: 0,
  selectedId: null,
  query: "",
  genre: "",
};

const els = {
  count: document.querySelector("#book-count"),
  search: document.querySelector("#search-input"),
  genre: document.querySelector("#genre-select"),
  summary: document.querySelector("#result-summary"),
  pageSummary: document.querySelector("#page-summary"),
  list: document.querySelector("#book-list"),
  prev: document.querySelector("#prev-button"),
  next: document.querySelector("#next-button"),
  pages: document.querySelector("#page-buttons"),
  detailTitle: document.querySelector("#detail-title"),
  detailAuthor: document.querySelector("#detail-author"),
  detailTags: document.querySelector("#detail-tags"),
  detailDescription: document.querySelector("#detail-description"),
};

function initTelegram() {
  const tg = window.Telegram?.WebApp;
  if (!tg) return;

  tg.ready();
  tg.expand();
}

function normalize(value) {
  return String(value || "").trim().toLowerCase();
}

function pageCount() {
  return Math.max(1, Math.ceil(state.filtered.length / PAGE_SIZE));
}

function currentPageBooks() {
  const start = state.page * PAGE_SIZE;
  return state.filtered.slice(start, start + PAGE_SIZE);
}

function applyFilters() {
  const query = normalize(state.query);
  const genre = normalize(state.genre);

  state.filtered = state.books.filter((book) => {
    const queryMatch = !query
      || normalize(book.title).includes(query)
      || normalize(book.authors).includes(query);
    const genreMatch = !genre || (book.tags || []).some((tag) => normalize(tag) === genre);
    return queryMatch && genreMatch;
  });

  state.page = Math.min(state.page, pageCount() - 1);
  render();
}

function renderGenres() {
  for (const genre of state.genres) {
    const option = document.createElement("option");
    option.value = genre;
    option.textContent = genre;
    els.genre.append(option);
  }
}

function render() {
  const total = state.filtered.length;
  const pages = pageCount();
  const books = currentPageBooks();

  // Save scroll position to prevent jumping
  const scrollPos = window.scrollY;

  els.count.textContent = `${state.books.length} books`;
  els.summary.textContent = total === 1 ? "1 result" : `${total} results`;
  els.pageSummary.textContent = total ? `Page ${state.page + 1} of ${pages}` : "";

  renderList(books);
  renderPager(pages);
  renderSelected(books);

  // Restore scroll position
  window.scrollTo(0, scrollPos);
}

function renderList(books) {
  els.list.replaceChildren();

  if (!books.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "No books found.";
    els.list.append(empty);
    return;
  }

  books.forEach((book) => {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "book-row";
    if (book.id === state.selectedId) row.classList.add("is-active");

    const main = document.createElement("div");
    const title = document.createElement("div");
    title.className = "book-title";
    title.textContent = book.title;

    const author = document.createElement("div");
    author.className = "book-author";
    author.textContent = book.authors || "Unknown author";

    main.append(title, author);

    const tags = document.createElement("div");
    tags.className = "tag-row";
    for (const tag of (book.tags || []).slice(0, 2)) {
      const chip = document.createElement("span");
      chip.className = "tag";
      chip.textContent = tag;
      tags.append(chip);
    }

    row.append(main, tags);
    row.addEventListener("click", () => {
      state.selectedId = book.id;
      render();
    });
    els.list.append(row);
  });
}

function renderPager(pages) {
  els.prev.disabled = state.page <= 0;
  els.next.disabled = state.page >= pages - 1;
  els.pages.replaceChildren();

  const visiblePages = new Set([0, pages - 1, state.page]);
  for (let page = state.page - 2; page <= state.page + 2; page += 1) {
    if (page > 0 && page < pages - 1) visiblePages.add(page);
  }

  [...visiblePages].sort((a, b) => a - b).forEach((page) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = String(page + 1);
    if (page === state.page) button.classList.add("is-current");
    button.addEventListener("click", () => {
      state.page = page;
      render();
    });
    els.pages.append(button);
  });
}

function renderSelected(visibleBooks) {
  const selected = state.filtered.find((book) => book.id === state.selectedId) || visibleBooks[0];

  if (!selected) {
    els.detailTitle.textContent = "Choose a book";
    els.detailAuthor.textContent = "";
    els.detailTags.replaceChildren();
    els.detailDescription.textContent = "";
    return;
  }

  state.selectedId = selected.id;
  els.detailTitle.textContent = selected.title;
  els.detailAuthor.textContent = selected.authors || "Unknown author";
  els.detailDescription.textContent = selected.description || "No description available.";
  els.detailTags.replaceChildren();

  for (const tag of selected.tags || []) {
    const chip = document.createElement("span");
    chip.className = "tag";
    chip.textContent = tag;
    els.detailTags.append(chip);
  }
}

function bindEvents() {
  els.search.addEventListener("input", (event) => {
    state.query = event.target.value;
    state.page = 0;
    state.selectedId = null;
    applyFilters();
  });

  els.genre.addEventListener("change", (event) => {
    state.genre = event.target.value;
    state.page = 0;
    state.selectedId = null;
    applyFilters();
  });

  els.prev.addEventListener("click", () => {
    state.page = Math.max(0, state.page - 1);
    render();
  });

  els.next.addEventListener("click", () => {
    state.page = Math.min(pageCount() - 1, state.page + 1);
    render();
  });
}

async function loadCatalog() {
  const response = await fetch("catalog.json", { cache: "no-store" });
  if (!response.ok) throw new Error("Catalog failed to load");
  const payload = await response.json();
  state.books = payload.books || [];
  state.genres = payload.genres || [];
  state.filtered = state.books;
  renderGenres();
  render();
}

async function main() {
  initTelegram();
  bindEvents();

  try {
    await loadCatalog();
  } catch (error) {
    els.summary.textContent = "Catalog unavailable";
    els.list.innerHTML = '<div class="empty-state">catalog.json could not be loaded.</div>';
    els.prev.disabled = true;
    els.next.disabled = true;
  }
}

main();
